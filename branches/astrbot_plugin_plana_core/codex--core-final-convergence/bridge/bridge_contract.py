from __future__ import annotations

from dataclasses import asdict
from time import time
from typing import Any

from ..plugin.models import BridgeTaskRequest


class BridgeContract:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bridge_required": False,
            "bridge_plugin": "astrbot_plugin_plana_bridge_gateway",
            "direct_runtime_dependency": True,
            "internal_lan_mode": True,
        }
    def disabled_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "bridge_api_disabled",
            "status": self.status(),
        }

    def normalize_task(self, payload: dict[str, Any]) -> BridgeTaskRequest:
        task_payload = (
            payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        )
        return BridgeTaskRequest(
            task_id=str(payload.get("task_id") or task_payload.get("task_id") or ""),
            objective=str(
                payload.get("objective")
                or task_payload.get("objective")
                or payload.get("content")
                or ""
            ),
            source=str(payload.get("source", "bridge_gateway")),
            user_context=payload.get("user_context")
            or task_payload.get("user_context")
            or {},
            memory_context=payload.get("memory_context")
            or task_payload.get("memory_context")
            or [],
            constraints=payload.get("constraints")
            or task_payload.get("constraints")
            or [],
        )

    def describe_task(self, task: BridgeTaskRequest) -> dict[str, Any]:
        return asdict(task)

    def normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("kind", payload.get("type", ""))).strip()
        if kind not in {
            "memory_query",
            "task_delegate",
            "execution_observation",
            "result_report",
            "emotional_handoff",
            "context_sync",
            "workflow_request",
        }:
            kind = "unknown"
        return {
            "kind": kind,
            "request_id": str(payload.get("request_id", "")),
            "source": str(payload.get("source", "bridge_gateway")),
            "user_id": str(payload.get("user_id", "")),
            "scope_id": str(payload.get("scope_id", "global")),
            "content": str(payload.get("content", ""))[:1200],
            "payload": payload.get("payload")
            if isinstance(payload.get("payload"), dict)
            else {},
            "created_at": int(payload.get("created_at") or time()),
        }

    def result_report(
        self, request: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "kind": "result_report",
            "request_id": request.get("request_id", ""),
            "source": "plana",
            "target": request.get("source", "bridge_gateway"),
            "result": result,
            "created_at": int(time()),
        }
