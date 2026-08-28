from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from time import time
from typing import Any

from ..execution.remote_contract import (
    DELEGATE_CONTRACT_VERSION,
    serialize_remote_execution_metadata,
)
from ..execution.codex_bundle import normalize_codex_execution_bundle
from .delivery import normalize_delivery_context


CONTRACT_VERSION = DELEGATE_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class CodexDelegationRequest:
    text: str
    scope_id: str
    actor_id: str
    capability: str
    reason: str
    lane: str = "interactive"
    priority: int = 30
    dedupe_key: str = ""
    title: str = ""
    expected_outputs: tuple[str, ...] = ()
    callback: str = ""
    wake_source: str = ""
    turn_context: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    remote_execution: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        request_id = f"codex-{uuid.uuid4()}"
        title = self.title or self.text[:80] or self.capability
        payload = {
            "contract_version": CONTRACT_VERSION,
            "request_id": request_id,
            "type": "codex_delegate",
            "text": self.text[:1200],
            "title": title[:180],
            "scope_id": self.scope_id or "global",
            "actor_id": self.actor_id or "user",
            "capability": self.capability,
            "reason": self.reason,
            "lane": self.lane or "interactive",
            "priority": int(self.priority),
            "dedupe_key": self.dedupe_key[:160],
            "expected_outputs": list(self.expected_outputs)[:8],
            "callback": self.callback[:500],
            "wake_source": self.wake_source,
            "turn_context": dict(self.turn_context),
            "delivery_context": normalize_delivery_context(
                self.turn_context.get("delivery_context")
            ),
            "constraints": dict(self.constraints),
            "created_at": int(time()),
        }
        payload.update(serialize_remote_execution_metadata(self.remote_execution))
        constraints = payload["constraints"]
        bundle = constraints.get("execution_bundle") if isinstance(constraints, dict) else None
        if bundle is not None:
            normalized_bundle = normalize_codex_execution_bundle(bundle)
            payload["execution_bundle"] = normalized_bundle
            payload["task_skills"] = list(normalized_bundle.get("skill_snapshots") or [])
            payload["expected_artifacts"] = list(
                normalized_bundle.get("expected_artifacts") or payload["expected_outputs"]
            )
        return payload


@dataclass(frozen=True, slots=True)
class CodexDelegationResult:
    ok: bool
    delegated: bool = False
    request_id: str = ""
    task_id: int | None = None
    status: str = ""
    message: str = ""
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RemoteTaskDelegator:
    """Queues governed Codex delegation through the Bridge relay.

    Core never stores remote runner URLs or tokens. It only emits a bounded
    proactive payload; the Bridge Gateway remains the external auth boundary.
    """

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    @property
    def enabled(self) -> bool:
        return bool(self.runtime.config.get("assistant_remote_runner_enabled", False))

    def delegate(self, request: CodexDelegationRequest) -> CodexDelegationResult:
        if not self.enabled:
            return CodexDelegationResult(
                ok=False,
                status="disabled",
                error="assistant_remote_runner_disabled",
                message="Codex Runner 未启用，已保留本地执行/确认路径。",
            )
        queue = getattr(self.runtime, "proactive_queue", None)
        enqueue = getattr(queue, "enqueue", None)
        if not callable(enqueue):
            return CodexDelegationResult(
                ok=False,
                status="unavailable",
                error="proactive_queue_unavailable",
                message="无法创建 Codex 委派任务：Core 主动任务队列不可用。",
            )
        payload = request.payload()
        task_id = enqueue(
            request.scope_id or "global",
            "custom",
            json.dumps(payload, ensure_ascii=False),
            user_id=request.actor_id or "user",
            priority=request.priority,
            ttl_seconds=3600,
            lane=request.lane,
        )
        if task_id is None:
            return CodexDelegationResult(
                ok=False,
                status="queue_rejected",
                error="remote_delegate_queue_rejected",
                message="Codex 委派任务未能进入 Bridge relay 队列。",
                payload=payload,
            )
        store = getattr(self.runtime, "remote_task_runs", None)
        create = getattr(store, "create", None)
        if callable(create):
            create(
                request_id=str(payload["request_id"]),
                proactive_task_id=int(task_id),
                scope_id=request.scope_id or "global",
                actor_id=request.actor_id or "user",
                lane=request.lane,
                title=str(payload.get("title") or ""),
                payload=payload,
            )
        return CodexDelegationResult(
            ok=True,
            delegated=True,
            request_id=str(payload["request_id"]),
            task_id=int(task_id),
            status="queued",
            message=(
                "这个任务需要在后台执行端处理，我已经开始了。"
                "完成后会把结果直接发回来，你可以继续聊别的。"
            ),
            payload=payload,
        )

    async def cancel(self, run: dict[str, Any]) -> CodexDelegationResult:
        request_id = str(run.get("request_id") or "").strip()
        runner_run_id = str(run.get("runner_run_id") or "").strip()
        proactive_task_id = run.get("proactive_task_id")
        store = getattr(self.runtime, "remote_task_runs", None)
        update = getattr(store, "update", None)
        if not runner_run_id:
            queue = getattr(self.runtime, "proactive_queue", None)
            cancel_queued = getattr(queue, "cancel", None)
            try:
                task_id = int(proactive_task_id or 0)
            except (TypeError, ValueError):
                task_id = 0
            if task_id > 0 and callable(cancel_queued) and cancel_queued(task_id):
                if callable(update):
                    update(request_id, status="cancelled", result={"status": "cancelled"})
                return CodexDelegationResult(
                    ok=True,
                    delegated=True,
                    request_id=request_id,
                    task_id=task_id,
                    status="cancelled",
                    message="Codex 任务已在提交前取消。",
                )
            return CodexDelegationResult(
                ok=False,
                request_id=request_id,
                status="cancel_unavailable",
                error="runner_run_id_missing",
                message="任务尚未取得 Runner 标识，当前无法确认取消状态。",
            )
        bridge = self._active_bridge()
        relay = getattr(bridge, "codex_relay", None) if bridge is not None else None
        cancel_remote = getattr(relay, "cancel_runner_task", None)
        if not callable(cancel_remote):
            return CodexDelegationResult(
                ok=False,
                request_id=request_id,
                status="cancel_unavailable",
                error="bridge_cancel_unavailable",
                message="Bridge 当前无法连接 Codex 取消接口。",
            )
        if callable(update):
            update(
                request_id,
                status="cancelling",
                runner_run_id=runner_run_id,
                result={"cancel_requested_at": int(time())},
            )
        response = await cancel_remote(runner_run_id)
        result = response.get("result") if isinstance(response, dict) else {}
        if not isinstance(result, dict):
            result = {}
        status = str(result.get("status") or response.get("status") or "failed")
        ok = bool(response.get("ok")) and status in {"cancelling", "cancelled"}
        if bool(response.get("ok")) and status in {"succeeded", "failed"}:
            apply_terminal = getattr(store, "apply_terminal_result", None)
            terminal_error = str(result.get("error") or response.get("error") or "")
            if callable(apply_terminal):
                apply_terminal(
                    request_id,
                    status=status,
                    runner_run_id=runner_run_id,
                    error=terminal_error,
                    result=result or response,
                )
            return CodexDelegationResult(
                ok=True,
                delegated=True,
                request_id=request_id,
                status=status,
                message="任务已在 Codex Runner 结束，Core 状态已完成同步。",
                payload={**(result or response), "reconciled_terminal": True},
            )
        if callable(update):
            update(
                request_id,
                status=status if ok else str(run.get("status") or "submitted"),
                runner_run_id=runner_run_id,
                error="" if ok else str(response.get("error") or "cancel_failed"),
                result=result or response,
            )
        return CodexDelegationResult(
            ok=ok,
            delegated=True,
            request_id=request_id,
            status=status,
            message="Codex 任务已取消。" if status == "cancelled" else "已向 Codex 提交取消请求。",
            error="" if ok else str(response.get("error") or "cancel_failed"),
            payload=result or response,
        )

    def _active_bridge(self) -> Any:
        for module_name in (
            "data.plugins.astrbot_plugin_plana_bridge_gateway.bridge.filters",
            "astrbot_plugin_plana_bridge_gateway.bridge.filters",
        ):
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue
            getter = getattr(module, "active_bridge_gateway", None)
            if callable(getter):
                plugin = getter()
                if plugin is not None:
                    return plugin
        return None
