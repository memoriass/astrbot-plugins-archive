from __future__ import annotations

import inspect
import time
import uuid
from pathlib import Path
from typing import Any

import aiohttp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.platform import MessageType
from astrbot.api.star import Context, Star, StarTools
from quart import jsonify, request

from .auth import active_send_authorized, core_headers, gateway_authorized
from .core_inprocess import CoreInProcessAdapter
from .codex_relay import CodexRunnerRelay
from .idempotency import DeliveryIdempotencyLedger
from .filters import PlanaBridgeForwardFilter, set_active_bridge_gateway
from .proactive_loop import ProactiveDeliveryLoop
from .proactive_runtime import ProactiveRuntimeMixin
from .replies import reply_to_chain, send_reply
from ..plugin.config import normalize_config, safe_int


PAYLOAD_KINDS = {
    "memory_query",
    "result_report",
    "context_sync",
    "emotional_handoff",
}
class PlanaBridgeGatewayPlugin(ProactiveRuntimeMixin, Star):
    """External bridge layer for Plana Core."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = normalize_config(config)
        self.enabled = bool(self.config.get("enabled", True))
        self.internal_lan_mode = bool(self.config.get("internal_lan_mode", True))
        self.external_gateway_mode = bool(self.config.get("external_gateway_mode", False))
        self.api_token = str(self.config.get("api_token", "") or "")
        self.core_bridge_url = str(self.config.get("core_bridge_url", "") or "").strip()
        self.core_state_url = str(self.config.get("core_state_url", "") or "").strip()
        self.core_proactive_poll_url = str(
            self.config.get("core_proactive_poll_url", "") or ""
        ).strip()
        self.core_proactive_deliver_url = str(
            self.config.get("core_proactive_deliver_url", "") or ""
        ).strip()
        self.core_token = str(self.config.get("core_token", "") or "")
        self.core_auth_header = str(self.config.get("core_auth_header", "") or "").strip()
        self.timeout_seconds = int(self.config.get("timeout_seconds", 30) or 30)
        self.enable_nacho_forward = bool(self.config.get("enable_nacho_forward", False))
        self.nacho_sidecar_url = str(
            self.config.get("nacho_sidecar_url", "http://127.0.0.1:8765") or ""
        ).rstrip("/")
        self.nacho_message_endpoint = str(
            self.config.get("nacho_message_endpoint", "/api/astrbot/message") or ""
        )
        self.nacho_api_token = str(self.config.get("nacho_api_token", "") or "")
        self.listen_group = bool(self.config.get("listen_group", True))
        self.listen_private = bool(self.config.get("listen_private", True))
        self.listen_other = bool(self.config.get("listen_other", False))
        self.send_replies = bool(self.config.get("send_replies", True))
        self.proactive_poll_interval_seconds = safe_int(
            self.config.get("proactive_poll_interval_seconds", 10), 10, 2, 300
        )
        self.stop_pipeline_mode = str(
            self.config.get("stop_pipeline_mode", "handled") or "handled"
        )
        self.enable_active_send_api = bool(self.config.get("enable_active_send_api", False))
        self.active_send_token = str(self.config.get("active_send_token", "") or "")
        data_dir = Path(StarTools.get_data_dir("astrbot_plugin_plana_bridge_gateway"))
        self.delivery_ledger = DeliveryIdempotencyLedger(data_dir / "bridge_delivery.sqlite3")
        self.codex_relay = CodexRunnerRelay(
            enabled=bool(self.config.get("enable_codex_runner", False)),
            runner_url=str(self.config.get("codex_runner_url", "") or ""),
            runner_token=str(self.config.get("codex_runner_token", "") or ""),
            runner_id=str(self.config.get("codex_runner_id", "") or ""),
            runner_lanes=(
                self.config.get("codex_runner_lanes", [])
                if isinstance(self.config.get("codex_runner_lanes", []), list)
                else []
            ),
            runner_protocol_version=str(
                self.config.get("codex_runner_protocol_version", "plana.codex.runner.v1")
                or "plana.codex.runner.v1"
            ),
            access_policy=str(self.config.get("runner_access_policy", "lan_allowlist") or "lan_allowlist"),
            timeout_seconds=safe_int(self.config.get("codex_runner_submit_timeout_seconds", 5), 5, 1, 60),
            concurrency=safe_int(self.config.get("codex_runner_delivery_concurrency", 4), 4, 1, 16),
            result_callback_url=str(self.config.get("codex_result_callback_url", "") or ""),
            artifact_dir=data_dir / "codex_artifacts",
            result_handler=self._handle_codex_result_payload,
            observation_handler=self._handle_codex_observation_payload,
            session_getter=lambda: self._session,
        )
        self.core_inprocess = CoreInProcessAdapter()
        self.proactive_loop = ProactiveDeliveryLoop(
            enabled=bool(self.codex_relay.enabled or self.enable_nacho_forward),
            interval_seconds=self.proactive_poll_interval_seconds,
            poll=self._poll_core_proactive,
            deliver=self._deliver_proactive,
            mark=self._mark_core_delivered,
            mark_failed=self._mark_core_failed,
        )
        self._session: aiohttp.ClientSession | None = None
        self._codex_notified_results: set[str] = set()

    async def initialize(self) -> None:
        if not self.enabled:
            logger.info("Plana Bridge Gateway disabled")
            return
        set_active_bridge_gateway(self)
        self.delivery_ledger.initialize()
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=max(1, self.timeout_seconds))
        )
        self._register_web_apis()
        self.proactive_loop.start()
        if self.external_gateway_mode and not self.api_token:
            logger.warning(
                "Plana Bridge Gateway external mode enabled but api_token is empty; HTTP APIs will reject calls"
            )
        if self.enable_active_send_api and not self.active_send_token:
            logger.warning(
                "Plana Bridge Gateway active send API enabled but active_send_token is empty"
            )
        logger.info(
            "Plana Bridge Gateway initialized: internal_lan=%s external_gateway=%s nacho_forward=%s core=%s",
            self.internal_lan_mode,
            self.external_gateway_mode,
            self.enable_nacho_forward,
            self.core_bridge_url,
        )

    async def terminate(self) -> None:
        set_active_bridge_gateway(None)
        await self.proactive_loop.stop()
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        logger.info("Plana Bridge Gateway terminated")

    def _register_web_apis(self) -> None:
        self.context.register_web_api(
            "/plana_bridge_gateway/status",
            self._api_status,
            ["GET"],
            "Plana Bridge Gateway status",
        )
        self.context.register_web_api(
            "/plana_bridge_gateway/bridge",
            self._api_bridge,
            ["POST"],
            "Forward standard bridge payload to Plana Core",
        )
        self.context.register_web_api(
            "/plana_bridge_gateway/proactive/poll-deliver",
            self._api_proactive_poll_deliver,
            ["POST"],
            "Poll Plana Core proactive queue and deliver via Nacho sidecar",
        )
        self.context.register_web_api(
            "/plana_bridge_gateway/codex/result",
            self._api_codex_result,
            ["POST"],
            "Receive Codex Runner result report",
        )
        if self.enable_active_send_api:
            self.context.register_web_api(
                "/plana_bridge_gateway/nacho/send",
                self._api_nacho_send_message,
                ["POST"],
                "Send messages through AstrBot for external bot nodes",
            )

    @filter.custom_filter(PlanaBridgeForwardFilter, False, priority=10000)
    async def on_bridge_message(self, event: AstrMessageEvent):
        response = await self._forward_event_to_nacho(event)
        if not response:
            return
        plana_results = await self._relay_plana_requests(event, response)
        if plana_results:
            response["plana_results"] = plana_results
            await self._post_plana_results(await self._build_payload(event), plana_results)
        if self.send_replies and response.get("should_reply", False):
            for reply in response.get("replies", []):
                await send_reply(event, reply)
        if self._should_stop_pipeline(response):
            event.call_llm = True
            event.stop_event()
            yield

    async def _api_status(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        core_status = await self._core_state()
        return jsonify(
            {
                "ok": True,
                "enabled": self.enabled,
                "internal_lan_mode": self.internal_lan_mode,
                "external_gateway_mode": self.external_gateway_mode,
                "nacho_forward": self.enable_nacho_forward,
                "core_bridge_fallback_url": self.core_bridge_url,
                "core_in_process": self.core_inprocess.status(),
                "core_state": core_status,
                "session_active": self._session is not None and not self._session.closed,
                "active_send_api": self.enable_active_send_api,
                "codex_runner": self.codex_relay.status(),
                "proactive_delivery_loop": self.proactive_loop.status(),
                "payload_kinds": sorted(PAYLOAD_KINDS),
                "mcp_ready": True,
            }
        )

    async def _api_bridge(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        normalized = self._normalize_bridge_payload(payload)
        result = await self._call_core_bridge(normalized)
        return jsonify(result), 200 if result.get("ok") else 502

    async def _api_nacho_send_message(self):
        if not self._active_send_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        session = str(payload.get("session", ""))
        replies = payload.get("replies", [])
        if not session or not isinstance(replies, list):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        sent = 0
        for reply in replies:
            if isinstance(reply, dict):
                chain = reply_to_chain(reply)
                if chain and await self.context.send_message(session, chain):
                    sent += 1
        return jsonify({"ok": True, "sent": sent})

    async def _core_state(self) -> dict[str, Any]:
        in_process = self.core_inprocess.status()
        if in_process.get("ok"):
            return in_process
        if not self.core_state_url or not self._session:
            return {"ok": False, "error": "core_state_url_missing"}
        try:
            async with self._session.get(
                self.core_state_url,
                headers=self._core_headers(),
            ) as resp:
                data = await resp.json()
                return data if isinstance(data, dict) else {"ok": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _call_core_bridge(self, payload: dict[str, Any]) -> dict[str, Any]:
        in_process = await self.core_inprocess.payload(payload)
        if in_process is not None:
            return in_process
        if not self.core_bridge_url or not self._session:
            return {"ok": False, "error": "core_bridge_unavailable"}
        try:
            async with self._session.post(
                self.core_bridge_url,
                json=payload,
                headers=self._core_headers(),
            ) as resp:
                data = await resp.json()
                return data if isinstance(data, dict) else {"ok": False}
        except Exception as exc:
            logger.warning("Plana Bridge Gateway core call failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def _should_forward_event(self, event: AstrMessageEvent) -> bool:
        if not self.enabled or not self.enable_nacho_forward:
            return False
        message_type = event.get_message_type()
        if message_type == MessageType.GROUP_MESSAGE:
            return self.listen_group
        if message_type == MessageType.FRIEND_MESSAGE:
            return self.listen_private
        return self.listen_other

    async def _forward_event_to_nacho(
        self, event: AstrMessageEvent
    ) -> dict[str, Any] | None:
        payload = await self._build_payload(event)
        return await self._post_to_nacho(payload)

    async def _relay_plana_requests(
        self, event: AstrMessageEvent, response: dict[str, Any]
    ) -> list[dict[str, Any]]:
        requests = response.get("plana_requests", [])
        if not isinstance(requests, list):
            return []
        results = []
        for item in requests[:5]:
            if isinstance(item, dict):
                normalized = self._normalize_plana_payload(event, item)
                result = await self._call_core_bridge(normalized)
                results.append(
                    {
                        "request_id": normalized.get("request_id", ""),
                        "kind": normalized.get("kind", ""),
                        "ok": bool(result.get("ok", True)),
                        "response": result,
                    }
                )
        return results

    async def _post_plana_results(
        self, source_payload: dict[str, Any], results: list[dict[str, Any]]
    ) -> None:
        callback = str(source_payload.get("plana_result_endpoint", "") or "")
        if not callback:
            return
        payload = {
            "event_id": source_payload.get("event_id", ""),
            "timestamp": int(time.time()),
            "session_id": source_payload.get("session_id", ""),
            "scope_id": source_payload.get("unified_msg_origin", ""),
            "user_id": (source_payload.get("sender") or {}).get("user_id", ""),
            "plana_results": results,
        }
        await self._post_to_nacho(payload, endpoint=callback)

    async def _build_payload(self, event: AstrMessageEvent) -> dict[str, Any]:
        message_type = event.get_message_type()
        return {
            "event_id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "platform": event.get_platform_name(),
            "platform_id": event.get_platform_id(),
            "message_type": getattr(message_type, "value", str(message_type)),
            "session_id": event.get_session_id(),
            "unified_msg_origin": event.unified_msg_origin,
            "group_id": event.get_group_id(),
            "self_id": event.get_self_id(),
            "sender": {
                "user_id": event.get_sender_id(),
                "nickname": event.get_sender_name(),
                "role": getattr(event, "role", "member"),
            },
            "message": {
                "text": event.get_message_str(),
                "outline": event.get_message_outline(),
                "segments": await self._serialize_segments(event.get_messages()),
            },
            "is_wake": event.is_wake,
            "is_at_or_wake_command": event.is_at_or_wake_command,
            "plana_bridge": {
                "enabled": True,
                "endpoint": "gateway",
                "scope_id": event.unified_msg_origin,
                "user_id": event.get_sender_id(),
                "payload_kinds": sorted(PAYLOAD_KINDS),
            },
        }

    async def _serialize_segments(self, segments: list[Any]) -> list[dict[str, Any]]:
        serialized = []
        for segment in segments:
            try:
                if hasattr(segment, "to_dict"):
                    value = segment.to_dict()
                    serialized.append(await value if inspect.isawaitable(value) else value)
                elif hasattr(segment, "toDict"):
                    serialized.append(segment.toDict())
                else:
                    serialized.append({"type": type(segment).__name__, "repr": repr(segment)})
            except Exception as exc:
                serialized.append({"type": type(segment).__name__, "error": str(exc)})
        return serialized

    async def _post_to_nacho(
        self, payload: dict[str, Any], *, endpoint: str | None = None
    ) -> dict[str, Any] | None:
        if not self._session:
            return None
        target = endpoint or self.nacho_message_endpoint
        url = target if target.startswith(("http://", "https://")) else f"{self.nacho_sidecar_url}{target}"
        headers = {"Content-Type": "application/json"}
        if self.nacho_api_token:
            headers["Authorization"] = f"Bearer {self.nacho_api_token}"
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning("Plana Bridge Gateway sidecar HTTP %s", resp.status)
                    return None
                data = await resp.json()
        except Exception as exc:
            logger.warning("Plana Bridge Gateway sidecar request failed: %s", exc)
            return None
        return data if isinstance(data, dict) else None

    def _normalize_plana_payload(
        self, event: AstrMessageEvent, item: dict[str, Any]
    ) -> dict[str, Any]:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return self._normalize_bridge_payload(
            {
                "kind": item.get("kind", item.get("type", "memory_query")),
                "request_id": item.get("request_id") or str(uuid.uuid4()),
                "source": "nachobot",
                "user_id": item.get("user_id") or event.get_sender_id(),
                "scope_id": item.get("scope_id") or event.unified_msg_origin,
                "content": item.get("content", ""),
                "payload": payload,
                "created_at": item.get("created_at") or int(time.time()),
            }
        )

    def _normalize_bridge_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("kind", payload.get("type", ""))).strip()
        if kind not in PAYLOAD_KINDS:
            kind = "unknown"
        return {
            "kind": kind,
            "request_id": str(payload.get("request_id") or uuid.uuid4()),
            "source": str(payload.get("source", "gateway")),
            "user_id": str(payload.get("user_id", "")),
            "scope_id": str(payload.get("scope_id", "global") or "global"),
            "content": str(payload.get("content", ""))[:1200],
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            "created_at": int(payload.get("created_at") or time.time()),
        }

    def _should_stop_pipeline(self, response: dict[str, Any]) -> bool:
        if bool(response.get("stop_astrbot_pipeline", False)):
            return True
        has_reply = bool(response.get("should_reply") or response.get("replies"))
        if self.stop_pipeline_mode == "always":
            return True
        if self.stop_pipeline_mode == "handled":
            return bool(response.get("handled", False))
        if self.stop_pipeline_mode == "reply":
            return has_reply
        return False

    def _authorized(self) -> bool:
        return gateway_authorized(
            request,
            internal_lan_mode=self.internal_lan_mode,
            external_gateway_mode=self.external_gateway_mode,
            api_token=self.api_token,
        )

    def _active_send_authorized(self) -> bool:
        return active_send_authorized(request, self.active_send_token)

    def _core_headers(self) -> dict[str, str]:
        return core_headers(self.core_auth_header, self.core_token)
