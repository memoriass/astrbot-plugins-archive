from __future__ import annotations

from ipaddress import ip_address
from typing import Any
import uuid
from urllib.parse import urlparse

from astrbot.api import logger
from quart import jsonify, request

from .proactive_delivery import deliver_proactive_task_results
from ..plugin.config import safe_int


class ProactiveRuntimeMixin:
    async def _api_proactive_poll_deliver(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        limit = safe_int(payload.get("limit", 5), 5, 1, 20) if isinstance(payload, dict) else 5
        tasks = await self._poll_core_proactive(limit)
        results = await self._deliver_proactive(tasks)
        delivered = 0
        failed = 0
        for item in results:
            if item.ok and await self._mark_core_delivered(
                item.task_id,
                item.request_id,
                item.runner_run_id,
                item.result_finalized,
            ):
                delivered += 1
            elif not item.ok:
                failed += 1
                await self._mark_core_failed(
                    item.task_id,
                    item.error,
                    item.request_id,
                    item.runner_run_id,
                )
        return jsonify({"ok": True, "polled": len(tasks), "delivered": delivered, "failed": failed})

    async def _api_codex_result(self):
        if not self._runner_ingress_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = await self._handle_codex_result_payload(payload)
        return jsonify(result), 200 if result.get("ok", True) else 502

    async def _handle_codex_result_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = await self.codex_relay.prepare_result(payload)
        request_id = str(payload.get("request_id") or "")
        idempotency_key = str(
            payload.get("idempotency_key")
            or payload.get("runner_run_id")
            or payload.get("run_id")
            or request_id
        ).strip()
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"succeeded", "failed", "cancelled"}:
            status = "succeeded" if bool(payload.get("success", False)) else "failed"
        ingress_phase = "callback" if bool(payload.get("callback") or payload.get("callback_received")) else "poll"
        phase_record = self.delivery_ledger.record_phase(
            idempotency_key, ingress_phase, "succeeded", payload
        )
        if phase_record.get("conflict"):
            return {
                "ok": False,
                "error": f"{ingress_phase}_result_conflict",
                "idempotency_key": idempotency_key,
            }
        existing = self.delivery_ledger.terminal(idempotency_key)
        if existing:
            digest = self.delivery_ledger.payload_digest(payload)
            if existing["terminal_status"] != status or existing["payload_digest"] != digest:
                return {
                    "ok": False,
                    "error": "terminal_result_conflict",
                    "idempotency_key": idempotency_key,
                }
            return {
                "ok": True,
                "idempotent_replay": True,
                "notification_sent": bool(existing["notification_sent"]),
                "notification_suppressed": bool(payload.get("suppress_notification", False)),
            }
        summary = str(payload.get("result_summary") or payload.get("summary") or "")
        normalized = self._normalize_bridge_payload(
            {
                "kind": "result_report",
                "request_id": request_id or str(uuid.uuid4()),
                "source": "codex_runner",
                "scope_id": str(payload.get("scope_id") or "global"),
                "user_id": str(payload.get("actor_id") or ""),
                "content": summary,
                "payload": payload,
            }
        )
        core_result = await self._call_core_bridge(normalized)
        core_payload = (
            core_result.get("result")
            if isinstance(core_result.get("result"), dict)
            else {}
        )
        core_error = str(core_payload.get("error") or "").strip()
        if core_error:
            return {
                "ok": False,
                "error": core_error,
                "request_id": request_id,
                "notification_sent": False,
            }
        notification_sent = bool(core_payload.get("notification_sent", False))
        notification_suppressed = bool(payload.get("suppress_notification", False))
        terminal_record = {"ok": False}
        if bool(core_result.get("ok", True)):
            self.delivery_ledger.record_phase(
                idempotency_key, "terminal", "succeeded", payload
            )
            terminal_record = self.delivery_ledger.record_terminal(
                idempotency_key,
                status,
                payload,
            )
            if notification_sent:
                self.delivery_ledger.record_phase(
                    idempotency_key, "notification", "succeeded", payload
                )
                self.delivery_ledger.mark_notification_sent(idempotency_key)
        else:
            self.delivery_ledger.record_phase(
                idempotency_key, "terminal", "failed", payload
            )
            logger.warning(
                "Plana Bridge Gateway result handoff failed because Core persistence failed request_id=%s",
                request_id,
            )
        return {
            **core_result,
            "notification_sent": notification_sent,
            "notification_suppressed": notification_suppressed,
            "notification_owner": "core",
            "idempotency_key": idempotency_key,
            "idempotent_replay": bool(terminal_record.get("replay", False)),
        }

    async def _handle_codex_observation_payload(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id") or "").strip()
        normalized = self._normalize_bridge_payload(
            {
                "kind": "execution_observation",
                "request_id": request_id or str(uuid.uuid4()),
                "source": "codex_runner",
                "scope_id": str(payload.get("scope_id") or "global"),
                "user_id": str(payload.get("actor_id") or ""),
                "content": "",
                "payload": payload,
            }
        )
        result = await self._call_core_bridge(normalized)
        core_payload = result.get("result") if isinstance(result.get("result"), dict) else {}
        return {
            "ok": bool(result.get("ok", True)) and not bool(core_payload.get("error")),
            "request_id": request_id,
            "observation_transition": core_payload.get("observation_transition"),
        }
    async def _poll_core_proactive(self, limit: int) -> list[dict[str, Any]]:
        in_process = self.core_inprocess.poll_proactive(limit)
        if in_process is not None:
            return in_process
        if not self.core_proactive_poll_url or not self._session:
            return []
        try:
            async with self._session.post(
                self.core_proactive_poll_url,
                json={"limit": limit},
                headers=self._core_headers(),
            ) as resp:
                data = await resp.json()
        except Exception as exc:
            logger.warning("Plana Bridge Gateway proactive poll failed: %s", exc)
            return []
        tasks = data.get("tasks", []) if isinstance(data, dict) else []
        return [item for item in tasks if isinstance(item, dict)]

    async def _mark_core_delivered(
        self,
        task_id: int,
        request_id: str = "",
        runner_run_id: str = "",
        result_finalized: bool = False,
    ) -> bool:
        in_process = self.core_inprocess.mark_proactive_delivered(
            task_id,
            request_id=request_id,
            runner_run_id=runner_run_id,
            result_finalized=result_finalized,
        )
        if in_process is not None:
            return in_process
        if task_id <= 0 or not self.core_proactive_deliver_url or not self._session:
            return False
        try:
            async with self._session.post(
                self.core_proactive_deliver_url,
                json={
                    "task_id": task_id,
                    "request_id": request_id,
                    "runner_run_id": runner_run_id,
                    "status": "delivered",
                    "result_finalized": result_finalized,
                },
                headers=self._core_headers(),
            ) as resp:
                data = await resp.json()
                return bool(isinstance(data, dict) and data.get("ok"))
        except Exception as exc:
            logger.warning("Plana Bridge Gateway mark delivered failed: %s", exc)
            return False

    async def _mark_core_failed(
        self,
        task_id: int,
        error: str,
        request_id: str = "",
        runner_run_id: str = "",
    ) -> bool:
        in_process = self.core_inprocess.mark_proactive_failed(
            task_id, error, request_id=request_id, runner_run_id=runner_run_id
        )
        if in_process is not None:
            return in_process
        if task_id <= 0 or not self.core_proactive_deliver_url or not self._session:
            return False
        try:
            async with self._session.post(
                self.core_proactive_deliver_url,
                json={
                    "task_id": task_id,
                    "request_id": request_id,
                    "runner_run_id": runner_run_id,
                    "status": "failed",
                    "error": error,
                },
                headers=self._core_headers(),
            ) as resp:
                data = await resp.json()
                return bool(isinstance(data, dict) and data.get("ok"))
        except Exception as exc:
            logger.warning("Plana Bridge Gateway mark failed failed: %s", exc)
            return False

    async def _deliver_proactive(self, tasks: list[dict[str, Any]]):
        return await deliver_proactive_task_results(
            tasks,
            codex_relay=self.codex_relay,
            nacho_enabled=self.enable_nacho_forward,
            post_to_nacho=self._post_to_nacho,
        )

    def _runner_ingress_authorized(self) -> bool:
        if not self.internal_lan_mode:
            return self._authorized()
        remote = str(getattr(request, "remote_addr", "") or "").strip()
        try:
            address = ip_address(remote)
        except ValueError:
            return remote.lower() == "localhost"
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_loopback:
            return True
        host = str(urlparse(getattr(self.codex_relay, "runner_url", "")).hostname or "")
        try:
            allowed = ip_address(host)
        except ValueError:
            return False
        if allowed.version == 6 and allowed.ipv4_mapped is not None:
            allowed = allowed.ipv4_mapped
        return address == allowed


def _format_qbittorrent_torrents(result: dict[str, Any]) -> str:
    torrents = result.get("torrents") if isinstance(result.get("torrents"), list) else []
    count = safe_int(result.get("count", len(torrents)), len(torrents), 0, 100000)
    if not torrents:
        return "qBittorrent 当前没有下载任务。"
    lines = [f"qBittorrent 当前有 {count} 个任务："]
    for index, item in enumerate(torrents[:6], start=1):
        if not isinstance(item, dict):
            continue
        name = _clean_summary(item.get("name")) or "未命名任务"
        progress = item.get("progress")
        try:
            progress_text = f"{float(progress) * 100:.0f}%"
        except (TypeError, ValueError):
            progress_text = "未知进度"
        state = _torrent_state_label(item.get("state"))
        lines.append(f"{index}. {name}（{progress_text}，{state}）")
    if count > 6:
        lines.append(f"另外还有 {count - 6} 个任务没有展开。")
    return "\n".join(lines)


def _format_qbittorrent_transfer(result: dict[str, Any]) -> str:
    transfer = result.get("transfer") if isinstance(result.get("transfer"), dict) else result
    status = str(transfer.get("connection_status") or "unknown").strip().lower()
    status_label = {
        "connected": "连接正常",
        "firewalled": "受到防火墙限制",
        "disconnected": "未连接",
    }.get(status, status or "状态未知")
    down = _format_rate(transfer.get("download_speed"))
    up = _format_rate(transfer.get("upload_speed"))
    return f"qBittorrent 当前{status_label}，下载速度 {down}，上传速度 {up}。"


def _format_ani_subscriptions(result: dict[str, Any]) -> str:
    subscriptions = result.get("subscriptions") if isinstance(result.get("subscriptions"), list) else []
    count = safe_int(result.get("count", len(subscriptions)), len(subscriptions), 0, 100000)
    if not subscriptions:
        return "当前没有启用的 ANI-RSS 订阅。"
    lines = [f"当前有 {count} 个 ANI-RSS 订阅："]
    for index, item in enumerate(subscriptions[:8], start=1):
        if not isinstance(item, dict):
            continue
        title = _clean_summary(item.get("title") or item.get("name")) or "未命名订阅"
        enabled = bool(item.get("enabled", True))
        lines.append(f"{index}. {title}（{'已启用' if enabled else '已停用'}）")
    if count > 8:
        lines.append(f"另外还有 {count - 8} 个订阅没有展开。")
    return "\n".join(lines)


def _format_ncqq_result(capability: str, result: dict[str, Any]) -> str:
    if capability == "ncqq.list_instances":
        instances = result.get("instances") if isinstance(result.get("instances"), list) else []
        if not instances:
            return "当前没有发现 NCQQ 实例。"
        offline = [item for item in instances if isinstance(item, dict) and str(item.get("state") or item.get("status") or "").lower() not in {"online", "running", "connected"}]
        return f"共发现 {len(instances)} 个 NCQQ 实例，其中 {len(offline)} 个当前不在线。"
    summary = _clean_summary(result.get("result_summary") or result.get("summary"))
    return summary or "NCQQ 查询已经完成。"


def _torrent_state_label(value: Any) -> str:
    state = str(value or "").strip().lower()
    if "up" in state or "seed" in state:
        return "做种中"
    if "down" in state:
        return "下载中"
    if "pause" in state or "stop" in state:
        return "已暂停"
    if "error" in state:
        return "异常"
    return state or "状态未知"


def _format_rate(value: Any) -> str:
    speed = safe_int(value, 0, 0, 10**15)
    if speed < 1024:
        return f"{speed} B/s"
    if speed < 1024 * 1024:
        return f"{speed / 1024:.1f} KiB/s"
    return f"{speed / (1024 * 1024):.1f} MiB/s"


def _clean_summary(value: Any) -> str:
    return " ".join(str(value or "").split())[:1600]


def _format_bytes(size: int) -> str:
    value = max(0, int(size))
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"
