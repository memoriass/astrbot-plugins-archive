from __future__ import annotations

import json
import asyncio
import hashlib
from ipaddress import ip_address
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import aiohttp
from astrbot.api import logger

from .capability import ActionEnvelope, CapabilityError, CapabilityRegistry


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    task_id: int
    ok: bool
    request_id: str = ""
    runner_run_id: str = ""
    error: str = ""
    result_finalized: bool = False


class CodexRunnerRelay:
    """Forwards Core delegation payloads to an isolated Codex runner.

    The relay does not execute tasks, approve proposals, or write Core state.
    It only moves bounded `codex_delegate` payloads across the Bridge boundary.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        runner_url: str,
        runner_token: str,
        runner_id: str = "",
        runner_lanes: list[str] | None = None,
        runner_protocol_version: str = "plana.codex.runner.v1",
        access_policy: str,
        timeout_seconds: int,
        concurrency: int = 4,
        result_callback_url: str = "",
        artifact_dir: Path | None = None,
        result_handler: Any = None,
        observation_handler: Any = None,
        capability_registry: CapabilityRegistry | None = None,
        session_getter: Any,
    ) -> None:
        self.enabled = enabled
        self.runner_url = runner_url.strip()
        self.runner_token = runner_token.strip()
        self.runner_id = str(runner_id or "").strip()[:120]
        self.runner_lanes = sorted({str(item).strip()[:80] for item in (runner_lanes or []) if str(item).strip()})
        self.runner_protocol_version = str(runner_protocol_version or "plana.codex.runner.v1").strip()[:80]
        self.access_policy = (access_policy or "lan_allowlist").strip() or "lan_allowlist"
        self.timeout_seconds = max(1, min(int(timeout_seconds or 30), 600))
        self.concurrency = max(1, min(int(concurrency or 4), 16))
        self.result_callback_url = result_callback_url.strip()
        self.artifact_dir = artifact_dir
        if self.artifact_dir is not None:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._result_handler = result_handler
        self._observation_handler = observation_handler
        self._last_observations: dict[str, tuple[str, int, int]] = {}
        self._capability_registry = capability_registry
        self._session_getter = session_getter
        self._recent_failures: list[dict[str, Any]] = []

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.runner_url),
            "access_policy": self.access_policy,
            "runner_url_configured": bool(self.runner_url),
            "runner_token_configured": bool(self.runner_token),
            "runner_id": self.runner_id,
            "runner_lanes": self.runner_lanes,
            "runner_protocol_version": self.runner_protocol_version,
            "identity_configured": bool(self.runner_id),
            "result_callback_configured": bool(self.result_callback_url),
            "in_process_result_handler": callable(self._result_handler),
            "delivery_concurrency": self.concurrency,
            "recent_failures": list(self._recent_failures[-8:]),
            "executes_tasks": False,
            "relay_only": True,
            "delegate_versions": [1, 2],
            "local_capabilities": list(
                self._capability_registry.names() if self._capability_registry else ()
            ),
        }

    def is_codex_task(self, task: dict[str, Any]) -> bool:
        payload = self.task_payload(task)
        return str(payload.get("type") or "") == "codex_delegate"

    def task_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        raw = task.get("payload")
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str) or not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    async def deliver_tasks(self, tasks: list[dict[str, Any]]) -> list[DeliveryResult]:
        codex_tasks = [task for task in tasks if self.is_codex_task(task)]
        if not codex_tasks:
            return []
        semaphore = asyncio.Semaphore(self.concurrency)

        async def guarded(task: dict[str, Any]) -> DeliveryResult:
            async with semaphore:
                return await self._deliver_one(task)

        return list(await asyncio.gather(*(guarded(task) for task in codex_tasks)))

    async def _deliver_one(self, task: dict[str, Any]) -> DeliveryResult:
        task_id = self._task_id(task)
        payload = self.task_payload(task)
        request_id = str(payload.get("request_id") or "")
        if int(payload.get("delegate_version") or 1) == 2:
            return await self._deliver_v2(task_id, request_id, payload)
        if not self.enabled:
            return self._failed(task_id, request_id, "codex_runner_relay_disabled")
        if not self.runner_url:
            return self._failed(task_id, request_id, "codex_runner_url_missing")
        if self.access_policy == "lan_allowlist" and not self._runner_url_is_lan():
            return self._failed(task_id, request_id, "runner_url_not_lan")
        session = self._session_getter()
        if session is None:
            return self._failed(task_id, request_id, "http_session_unavailable")
        if self.result_callback_url and not payload.get("callback"):
            payload = {**payload, "callback": self.result_callback_url}
        headers = {
            "Content-Type": "application/json",
            "X-Plana-Gateway": "codex-relay",
        }
        if self.runner_token:
            headers["Authorization"] = f"Bearer {self.runner_token}"
        try:
            async with session.post(
                self.runner_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:  # noqa: BLE001
                    data = {}
                if resp.status >= 400:
                    runner_error = str(data.get("error") or "").strip() if isinstance(data, dict) else ""
                    lane = str(data.get("lane") or "").strip() if isinstance(data, dict) else ""
                    detail = f"{runner_error}:{lane}" if runner_error and lane else runner_error
                    return self._failed(
                        task_id,
                        request_id,
                        detail or f"runner_http_{resp.status}",
                    )
                if isinstance(data, dict) and data.get("executes_tasks") is False:
                    return self._failed(task_id, request_id, "runner_simulation_only")
                runner_run_id = ""
                if isinstance(data, dict):
                    runner_run_id = str(data.get("run_id") or "")
                result = DeliveryResult(
                    task_id=task_id,
                    ok=True,
                    request_id=request_id,
                    runner_run_id=runner_run_id,
                )
                if runner_run_id and callable(self._result_handler) and not payload.get("callback"):
                    asyncio.create_task(self._poll_runner_result(payload, runner_run_id))
                return result
        except Exception as exc:  # noqa: BLE001
            return self._failed(task_id, request_id, str(exc))

    async def _deliver_v2(
        self,
        task_id: int,
        request_id: str,
        payload: dict[str, Any],
    ) -> DeliveryResult:
        if self._capability_registry is None:
            return self._failed(task_id, request_id, "capability_registry_unavailable")
        try:
            envelope = ActionEnvelope.from_payload(payload)
            result = await self._capability_registry.execute(envelope)
        except CapabilityError as exc:
            return self._failed(task_id, request_id, str(exc))
        handler = self._result_handler
        if callable(handler):
            await handler(
                {
                    "request_id": request_id,
                    "scope_id": str(payload.get("scope_id") or "global"),
                    "actor_id": str(payload.get("actor_id") or ""),
                    "delivery_context": payload.get("delivery_context")
                    if isinstance(payload.get("delivery_context"), dict)
                    else {},
                    "status": "succeeded",
                    "success": True,
                    "result_summary": str(
                        result.get("result_summary") or f"{envelope.capability} completed"
                    ),
                    "result": result,
                    "delegate_version": 2,
                    "service_ref": envelope.service_ref,
                    "capability": envelope.capability,
                    "suppress_notification": bool((payload.get("constraints") or {}).get("suppress_notification", False)),
                }
            )
        return DeliveryResult(
            task_id=task_id,
            ok=True,
            request_id=request_id,
            result_finalized=True,
        )

    def _task_id(self, task: dict[str, Any]) -> int:
        try:
            return int(task.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    def _failed(self, task_id: int, request_id: str, error: str) -> DeliveryResult:
        clean_error = " ".join(str(error or "delivery_failed").split())[:300]
        logger.warning("Codex Runner relay failed task_id=%s error=%s", task_id, clean_error)
        self._recent_failures.append(
            {"task_id": task_id, "request_id": request_id, "error": clean_error}
        )
        self._recent_failures = self._recent_failures[-20:]
        return DeliveryResult(task_id=task_id, ok=False, request_id=request_id, error=clean_error)

    async def _poll_runner_result(
        self,
        payload: dict[str, Any],
        runner_run_id: str,
    ) -> None:
        session = self._session_getter()
        handler = self._result_handler
        if session is None or not callable(handler):
            return
        url = self._runner_result_url(runner_run_id)
        if not url:
            return
        headers = {"X-Plana-Gateway": "codex-relay"}
        if self.runner_token:
            headers["Authorization"] = f"Bearer {self.runner_token}"
        for _attempt in range(260):
            await asyncio.sleep(0.5)
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 404:
                        continue
                    if resp.status >= 400:
                        self._failed(0, str(payload.get("request_id") or ""), f"result_http_{resp.status}")
                        return
                    data = await resp.json()
            except Exception as exc:  # noqa: BLE001
                self._failed(0, str(payload.get("request_id") or ""), f"result_poll_failed:{exc}")
                return
            result = data.get("result") if isinstance(data, dict) else None
            if not isinstance(result, dict):
                continue
            if str(result.get("status") or "") in {"queued", "running", "cancelling"}:
                await self._report_runner_observation(payload, result)
                continue
            result.setdefault("request_id", payload.get("request_id"))
            result.setdefault("scope_id", payload.get("scope_id"))
            result.setdefault("actor_id", payload.get("actor_id"))
            result.setdefault("delivery_context", payload.get("delivery_context"))
            await handler(result)
            return

    async def _report_runner_observation(
        self,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        handler = self._observation_handler
        if not callable(handler):
            return
        run_id = str(result.get("runner_run_id") or result.get("run_id") or "")
        marker = (
            str(result.get("status") or ""),
            int(result.get("event_seq") or 0),
            int(result.get("heartbeat_at") or 0),
        )
        if self._last_observations.get(run_id) == marker:
            return
        self._last_observations[run_id] = marker
        observation = dict(result)
        observation.setdefault("request_id", payload.get("request_id"))
        observation.setdefault("scope_id", payload.get("scope_id"))
        observation.setdefault("actor_id", payload.get("actor_id"))
        await handler(observation)

    async def prepare_result(self, result: dict[str, Any]) -> dict[str, Any]:
        runner_run_id = str(result.get("runner_run_id") or result.get("run_id") or "").strip()
        if not runner_run_id:
            return result
        artifacts = result.get("artifacts")
        if isinstance(artifacts, list) and any(
            isinstance(item, dict) and item.get("transferred") for item in artifacts
        ):
            return result
        return await self._download_result_artifacts(result, runner_run_id)

    async def _download_result_artifacts(
        self,
        result: dict[str, Any],
        runner_run_id: str,
    ) -> dict[str, Any]:
        artifacts = result.get("artifacts")
        if self.artifact_dir is None or not isinstance(artifacts, list):
            return result
        downloaded: list[dict[str, Any]] = []
        for index, artifact in enumerate(artifacts[:16]):
            if isinstance(artifact, dict):
                downloaded.append(await self._download_artifact(runner_run_id, artifact, index))
        return {**result, "artifacts": downloaded}

    async def _download_artifact(
        self,
        runner_run_id: str,
        artifact: dict[str, Any],
        index: int,
    ) -> dict[str, Any]:
        artifact_id = str(artifact.get("artifact_id") or artifact.get("sha256") or "").strip()
        expected_sha256 = str(artifact.get("sha256") or "").strip().lower()
        expected_bytes = int(artifact.get("bytes") or 0)
        if not artifact_id or expected_bytes < 0 or expected_bytes > 100 * 1024 * 1024:
            return {**artifact, "transfer_error": "artifact_metadata_invalid"}
        url = self._runner_artifact_url(runner_run_id, artifact_id)
        session = self._session_getter()
        if not url or session is None:
            return {**artifact, "transfer_error": "artifact_transport_unavailable"}
        run_dir = self.artifact_dir / _safe_name(runner_run_id, "run")
        run_dir.mkdir(parents=True, exist_ok=True)
        name = _safe_name(str(artifact.get("name") or ""), f"artifact-{index + 1}")
        target = run_dir / name
        headers = {"X-Plana-Gateway": "codex-relay"}
        if self.runner_token:
            headers["Authorization"] = f"Bearer {self.runner_token}"
        digest = hashlib.sha256()
        received = 0
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=max(self.timeout_seconds, 120)),
            ) as resp:
                if resp.status >= 400:
                    return {**artifact, "transfer_error": f"artifact_http_{resp.status}"}
                with target.open("wb") as handle:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        received += len(chunk)
                        if received > 100 * 1024 * 1024:
                            raise ValueError("artifact_too_large")
                        digest.update(chunk)
                        handle.write(chunk)
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            return {**artifact, "transfer_error": str(exc)[:160]}
        actual_sha256 = digest.hexdigest()
        if received != expected_bytes or (expected_sha256 and actual_sha256 != expected_sha256):
            target.unlink(missing_ok=True)
            return {**artifact, "transfer_error": "artifact_integrity_mismatch"}
        return {
            **artifact,
            "path": str(target),
            "local_path": str(target),
            "bytes": received,
            "sha256": actual_sha256,
            "transferred": True,
        }

    async def cancel_runner_task(self, runner_run_id: str) -> dict[str, Any]:
        clean_run_id = str(runner_run_id or "").strip()
        if not self.enabled:
            return {"ok": False, "status": "unavailable", "error": "codex_runner_relay_disabled"}
        if not clean_run_id:
            return {"ok": False, "status": "invalid", "error": "runner_run_id_missing"}
        if self.access_policy == "lan_allowlist" and not self._runner_url_is_lan():
            return {"ok": False, "status": "rejected", "error": "runner_url_not_lan"}
        session = self._session_getter()
        if session is None:
            return {"ok": False, "status": "unavailable", "error": "http_session_unavailable"}
        url = self._runner_cancel_url(clean_run_id)
        if not url:
            return {"ok": False, "status": "invalid", "error": "runner_url_invalid"}
        headers = {"Content-Type": "application/json", "X-Plana-Gateway": "codex-relay"}
        if self.runner_token:
            headers["Authorization"] = f"Bearer {self.runner_token}"
        try:
            async with session.post(
                url,
                json={},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:  # noqa: BLE001
                    data = {}
                if resp.status == 404:
                    return {"ok": False, "status": "not_found", "error": "runner_task_not_found"}
                if resp.status >= 400:
                    error = str(data.get("error") or f"runner_http_{resp.status}")
                    return {"ok": False, "status": "failed", "error": error}
                return data if isinstance(data, dict) else {"ok": True, "status": "cancelling"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": "failed", "error": str(exc)[:300]}

    def _runner_result_url(self, runner_run_id: str) -> str:
        parsed = urlparse(self.runner_url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return urlunparse(
            parsed._replace(path=f"/plana/codex/result/{runner_run_id}", query="")
        )

    def _runner_cancel_url(self, runner_run_id: str) -> str:
        parsed = urlparse(self.runner_url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return urlunparse(
            parsed._replace(path=f"/plana/codex/cancel/{runner_run_id}", query="")
        )

    def _runner_artifact_url(self, runner_run_id: str, artifact_id: str) -> str:
        parsed = urlparse(self.runner_url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        run_part = quote(str(runner_run_id or "").strip(), safe="")
        artifact_part = quote(str(artifact_id or "").strip(), safe="")
        return urlunparse(
            parsed._replace(path=f"/plana/codex/artifact/{run_part}/{artifact_part}", query="")
        )

    def _runner_url_is_lan(self) -> bool:
        parsed = urlparse(self.runner_url)
        host = (parsed.hostname or "").strip()
        if host.lower() == "localhost":
            return True
        try:
            address = ip_address(host)
        except ValueError:
            return False
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        return bool(address.is_loopback or address.is_private)


def _safe_name(value: str, fallback: str) -> str:
    name = Path(str(value or "").replace("\\", "/")).name.strip().replace("\x00", "")
    for char in '<>:"/\\|?*':
        name = name.replace(char, "_")
    return name if name not in {"", ".", ".."} else fallback
