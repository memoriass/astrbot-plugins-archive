"""Built-in NachoBot Sidecar bridge client for Plana Core.

Replaces the standalone astrbot_plugin_nacho_bridge plugin by embedding
the sidecar communication logic directly into PlanaCore, controlled via
the nacho_bridge config group.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import MessageType


class NachoSidecarBridge:
    """Manages HTTP communication with a NachoBot Sidecar instance."""

    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enable_nacho_bridge", False))
        self.sidecar_url = str(
            config.get("nacho_sidecar_url", "http://127.0.0.1:8765")
        ).rstrip("/")
        self.message_endpoint = str(
            config.get("nacho_message_endpoint", "/api/astrbot/message")
        )
        self.api_token = str(config.get("nacho_api_token", ""))
        self.timeout_seconds = int(config.get("nacho_timeout_seconds", 30))
        self.listen_group = bool(config.get("nacho_listen_group", True))
        self.listen_private = bool(config.get("nacho_listen_private", True))
        self.listen_other = bool(config.get("nacho_listen_other", False))
        self.send_replies = bool(config.get("nacho_send_replies", True))
        self.stop_pipeline_mode = str(config.get("nacho_stop_pipeline_mode", "handled"))
        self.debug_log_payload = bool(config.get("nacho_debug_log_payload", False))
        self.enable_active_send_api = bool(
            config.get("nacho_enable_active_send_api", True)
        )
        self.active_send_token = str(config.get("nacho_active_send_token", ""))
        # PlanaCore bridge relay (sidecar -> PlanaCore)
        self.enable_plana_relay = bool(config.get("nacho_enable_plana_relay", True))
        self.plana_result_endpoint = str(
            config.get("nacho_plana_result_endpoint", "")
        ).strip()
        self.plana_result_token = str(config.get("nacho_plana_result_token", ""))
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if not self.enabled:
            return
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        logger.info(
            "Nacho sidecar bridge started: %s%s",
            self.sidecar_url,
            self.message_endpoint,
        )

    async def stop(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def should_forward_event(self, event: AstrMessageEvent) -> bool:
        if not self.enabled:
            return False
        message_type = event.get_message_type()
        if message_type == MessageType.GROUP_MESSAGE:
            return self.listen_group
        if message_type == MessageType.FRIEND_MESSAGE:
            return self.listen_private
        return self.listen_other

    async def forward_event(self, event: AstrMessageEvent) -> dict[str, Any] | None:
        """Forward an event to the NachoBot Sidecar and return its response."""
        if not self._session:
            return None
        payload = await self._build_payload(event)
        return await self._post_to_sidecar(payload)

    async def relay_plana_requests(
        self,
        event: AstrMessageEvent,
        response: dict[str, Any],
        bridge_handler,
    ) -> list[dict[str, Any]]:
        """Relay plana_requests from sidecar response to PlanaCore bridge handler."""
        if not self.enable_plana_relay or not self._session:
            return []
        requests = response.get("plana_requests", [])
        if not isinstance(requests, list):
            return []
        results = []
        for item in requests[:5]:
            if isinstance(item, dict):
                normalized = self._normalize_plana_payload(event, item)
                result = bridge_handler(normalized)
                results.append(
                    {
                        "request_id": normalized.get("request_id", ""),
                        "kind": normalized.get("kind", ""),
                        "ok": bool(result),
                        "response": result or {},
                    }
                )
        return results

    async def post_plana_results(
        self, source_payload: dict[str, Any], results: list[dict[str, Any]]
    ) -> None:
        """Optionally callback sidecar with PlanaCore results."""
        url = self._plana_result_callback_url()
        if not url or not self._session:
            return
        headers = {"Content-Type": "application/json"}
        token = self.plana_result_token or self.api_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = {
            "event_id": source_payload.get("event_id", ""),
            "timestamp": int(time.time()),
            "session_id": source_payload.get("session_id", ""),
            "scope_id": source_payload.get("unified_msg_origin", ""),
            "user_id": (source_payload.get("sender") or {}).get("user_id", ""),
            "plana_results": results,
        }
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "Nacho bridge plana result callback returned HTTP %s",
                        resp.status,
                    )
        except Exception as exc:
            logger.warning("Nacho bridge plana result callback failed: %s", exc)

    async def send_reply(self, event: AstrMessageEvent, reply: dict[str, Any]) -> None:
        chain = self._reply_to_chain(reply)
        if chain:
            await event.send(chain)

    def should_stop_pipeline(self, response: dict[str, Any]) -> bool:
        if bool(response.get("stop_astrbot_pipeline", False)):
            return True
        mode = self.stop_pipeline_mode
        has_reply = bool(response.get("should_reply") or response.get("replies"))
        if mode == "always":
            return True
        if mode == "handled":
            return bool(response.get("handled", False))
        if mode == "reply":
            return has_reply
        return False

    def active_token_authorized(self, token: str) -> bool:
        if not self.active_send_token:
            return True
        import secrets

        return secrets.compare_digest(token, self.active_send_token)

    def status_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "sidecar_url": self.sidecar_url,
            "message_endpoint": self.message_endpoint,
            "listen_group": self.listen_group,
            "listen_private": self.listen_private,
            "send_replies": self.send_replies,
            "stop_pipeline_mode": self.stop_pipeline_mode,
            "enable_active_send_api": self.enable_active_send_api,
            "enable_plana_relay": self.enable_plana_relay,
            "session_active": self._session is not None and not self._session.closed,
        }

    async def deliver_proactive(self, tasks: list[dict[str, Any]]) -> int:
        """Deliver ready proactive tasks via sidecar callback endpoint.

        Returns the number of tasks successfully acknowledged by sidecar.
        Does nothing if bridge is disabled or no session is active.
        """
        if not tasks or not self._session or not self.enabled:
            return 0
        url = self._plana_result_callback_url()
        if not url:
            return 0
        headers = {"Content-Type": "application/json"}
        token = self.plana_result_token or self.api_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = {
            "event_id": f"proactive-{uuid.uuid4()}",
            "timestamp": int(time.time()),
            "session_id": "",
            "scope_id": "",
            "user_id": "",
            "proactive_tasks": tasks,
        }
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "Nacho bridge proactive delivery returned HTTP %s", resp.status
                    )
                    return 0
                return len(tasks)
        except Exception as exc:
            logger.warning("Nacho bridge proactive delivery failed: %s", exc)
            return 0

    # -- internal --

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
            "plana_bridge": self._plana_context_hint(event),
        }

    def _plana_context_hint(self, event: AstrMessageEvent) -> dict[str, Any]:
        return {
            "enabled": self.enable_plana_relay,
            "endpoint": "builtin",
            "scope_id": event.unified_msg_origin,
            "user_id": event.get_sender_id(),
            "payload_kinds": [
                "memory_query",
                "task_delegate",
                "result_report",
                "context_sync",
                "emotional_handoff",
            ],
        }

    async def _serialize_segments(self, segments: list[Any]) -> list[dict[str, Any]]:
        serialized = []
        for segment in segments:
            try:
                if hasattr(segment, "to_dict"):
                    serialized.append(await segment.to_dict())
                elif hasattr(segment, "toDict"):
                    serialized.append(segment.toDict())
                else:
                    serialized.append(
                        {"type": type(segment).__name__, "repr": repr(segment)}
                    )
            except Exception as exc:
                serialized.append({"type": type(segment).__name__, "error": str(exc)})
        return serialized

    async def _post_to_sidecar(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self._session:
            return None
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        url = f"{self.sidecar_url}{self.message_endpoint}"
        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    logger.warning("Nacho sidecar bridge returned HTTP %s", resp.status)
                    return None
                data = await resp.json()
        except Exception as exc:
            logger.warning("Nacho sidecar bridge request failed: %s", exc)
            return None
        if self.debug_log_payload:
            logger.info(
                "Nacho bridge event=%s handled=%s replies=%s",
                payload.get("event_id"),
                data.get("handled"),
                len(data.get("replies", [])),
            )
        return data if isinstance(data, dict) else None

    def _normalize_plana_payload(
        self, event: AstrMessageEvent, item: dict[str, Any]
    ) -> dict[str, Any]:
        kind = str(item.get("kind", item.get("type", "memory_query")))
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return {
            "kind": kind,
            "request_id": str(item.get("request_id") or uuid.uuid4()),
            "source": "nachobot",
            "user_id": str(item.get("user_id") or event.get_sender_id()),
            "scope_id": str(item.get("scope_id") or event.unified_msg_origin),
            "content": str(item.get("content", ""))[:1200],
            "payload": payload,
            "created_at": int(item.get("created_at") or time.time()),
        }

    def _plana_result_callback_url(self) -> str:
        endpoint = self.plana_result_endpoint
        if not endpoint:
            return ""
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return f"{self.sidecar_url}{path}"

    def _reply_to_chain(self, reply: dict[str, Any]) -> MessageChain | None:
        reply_type = str(reply.get("type", "text"))
        chain = MessageChain()
        if reply_type == "text":
            text = str(reply.get("text", ""))
            return chain.message(text) if text else None
        if reply_type == "image_url":
            return chain.url_image(str(reply.get("url", "")))
        if reply_type == "image_file":
            return chain.file_image(str(reply.get("path", "")))
        if reply_type == "image_base64":
            return chain.base64_image(str(reply.get("base64", "")))
        logger.warning("Unsupported Nacho reply type: %s", reply_type)
        return None
