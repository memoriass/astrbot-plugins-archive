from __future__ import annotations

from time import time
from typing import Any

from .task_broker_models import AssistantTaskRequest, AssistantTaskResult
from .task_route_decider import TaskRouteDecision
from .task_session import TaskRouteTrace


class AssistantTaskRouterSupportMixin:
    def observe_model_response(self, event: Any, text: str) -> None:
        self.session_service.observe_model_response(self.runtime, event, text)

    def _handoff_llm_tool(
        self,
        request: AssistantTaskRequest,
        scope_id: str,
        actor_id: str,
        route: TaskRouteDecision,
    ) -> AssistantTaskResult:
        setattr(request.event, "is_at_or_wake_command", True)
        tool_profile = str(route.metadata.get("tool_profile") or "")
        setattr(request.event, "_plana_native_tool_profile", tool_profile)
        setattr(request.event, "_plana_native_risk_class", str(route.metadata.get("risk_class") or ""))
        self._record(
            request,
            scope_id,
            actor_id,
            action="handoff_llm_tool",
            capability=route.capability,
            status="pass_to_llm",
            reason=route.reason,
            expected_capability=route.capability,
            route_name="native_tool",
            tool_profile=tool_profile,
            risk_class=str(route.metadata.get("risk_class") or ""),
        )
        return AssistantTaskResult(True, "", False, "handoff_llm_tool")

    def _delegate_remote(
        self,
        request: AssistantTaskRequest,
        scope_id: str,
        actor_id: str,
        route: TaskRouteDecision,
    ) -> AssistantTaskResult:
        proposal = self.propose_remote_authorization(
            event=request.event,
            goal=request.text,
            reason=route.remote_reason or route.reason,
            capability=route.capability,
            lane=route.lane,
            read_only=False,
        )
        pending = proposal.get("status") == "waiting_user_authorization"
        reply = (
            "这个任务需要交给受控 Codex 执行。当前只生成授权提案，不会直接读取或修改；"
            "回复“可以”后才会提交，回复“取消”可撤销。"
            if pending
            else "Codex 授权提案生成失败，任务没有提交。"
        )
        self._record(
            request,
            scope_id,
            actor_id,
            action="remote_delegate",
            capability=route.capability,
            status="waiting_authorization" if pending else "remote_unavailable",
            reason=str(proposal.get("error") or route.reason),
            recovery=reply,
            remote_reason=route.remote_reason,
            expected_capability=route.capability,
            route_name="codex",
            risk_class=str(route.metadata.get("risk_class") or "delegated_external"),
        )
        return AssistantTaskResult(True, reply, True, str(proposal.get("error") or route.reason))

    def propose_remote_authorization(
        self,
        *,
        event: Any,
        goal: str,
        reason: str,
        capability: str,
        lane: str,
        read_only: bool,
        service_ref: str = "codex.runner",
        credential_ref: str = "",
    ) -> dict[str, Any]:
        scope_id = str(self.runtime.resolve_scope(event.unified_msg_origin) or "global")
        try:
            actor_id = str(self.runtime.identity_from_event(event).global_user_id or "user")
        except Exception:  # noqa: BLE001
            actor_id = str(getattr(event, "get_sender_id", lambda: "user")() or "user")
        clean_goal = " ".join(str(goal or "").split())[:500]
        clean_capability = str(capability or "").strip()
        if not clean_goal:
            return {"status": "invalid_request", "error": "execution_goal_missing"}
        if clean_capability not in {"codex.interactive", "codex.long_task"}:
            return {"status": "capability_unavailable", "error": "codex_capability_required"}
        clean_lane = str(lane or "interactive").strip().lower()
        if clean_lane not in {"interactive", "long"}:
            clean_lane = "interactive"
        state = self.sessions.session(scope_id, actor_id)
        execution_context = self.execution_contexts.create(
            scope_id=scope_id,
            actor_id=actor_id,
            original_task=clean_goal,
            service_ref=service_ref or "codex.runner",
            capability=clean_capability,
            credential_ref=credential_ref,
            lane=clean_lane,
            read_only=read_only,
            reason=reason,
        )
        state.latest_prompt = clean_goal
        state.latest_expected_capability = clean_capability
        state.latest_remote_authorization_pending = True
        state.latest_remote_lane = execution_context.lane
        state.latest_remote_reason = str(reason or "controlled_external_execution")[:200]
        state.latest_execution_context_id = execution_context.context_id
        state.latest_service_ref = execution_context.service_ref
        state.current_goal = clean_goal
        state.updated_at = time()
        self.sessions.persist(state)
        return {
            "status": "waiting_user_authorization",
            "goal": clean_goal,
            "capability": clean_capability,
            "lane": execution_context.lane,
            "read_only": execution_context.read_only,
        }

    async def auto_authorize_readonly(self, event: Any) -> dict[str, Any]:
        del event
        return {"status": "authorization_required"}

    def _record(
        self,
        request: AssistantTaskRequest,
        scope_id: str,
        actor_id: str,
        *,
        action: str,
        capability: str,
        status: str,
        run_id: int | None = None,
        sandbox: str = "",
        reason: str = "",
        recovery: str = "",
        remote_reason: str = "",
        expected_capability: str = "",
        route_name: str = "",
        tool_profile: str = "",
        risk_class: str = "",
        artifact_count: int = 0,
        clarification_count: int = 0,
    ) -> None:
        self.sessions.record_trace(
            TaskRouteTrace(
                scope_id=scope_id,
                actor_id=actor_id,
                text=request.text,
                wake_source=request.wake.source,
                preflight_source=request.preflight_source,
                preflight_reason=request.preflight_reason,
                route=route_name or request.decision.route,
                intent=request.decision.intent,
                action=action,
                capability=capability,
                status=status,
                run_id=run_id,
                sandbox=sandbox,
                reason=reason,
                recovery=recovery,
                expected_capability=expected_capability,
                remote_reason=remote_reason,
                tool_profile=tool_profile,
                risk_class=risk_class,
                artifact_count=artifact_count,
                clarification_count=clarification_count,
            )
        )
