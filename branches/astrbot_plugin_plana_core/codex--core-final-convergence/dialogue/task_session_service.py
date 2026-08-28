from __future__ import annotations

import re
from typing import Any

from .delivery import delivery_context_from_event
from .remote_task import CodexDelegationRequest, RemoteTaskDelegator
from .task_response_composer import TaskResponseComposer
from .task_session_models import NaturalTaskAction
from .task_session_support import TaskSessionSupportMixin
from .task_session import TaskSessionStore


class TaskSessionService(TaskSessionSupportMixin):
    _CONFIRM_RE = re.compile(
        r"^(确认|确认执行|继续|继续执行|可以|可以执行|同意|执行吧|运行吧|yes|y|ok|okay|approve)$",
        re.IGNORECASE,
    )
    _RETRY_RE = re.compile(r"^(重试|再试一次|retry)$", re.IGNORECASE)
    _CANCEL_RE = re.compile(
        r"^(?:(?:取消|取消执行|取消任务|取消刚才的任务|不用了|不要了|别执行了|别继续了|停止|停一下|算了|stop|cancel|no)(?:[，,。！!\s]+.*)?|(?:不需要继续|不用继续|别再继续|不要继续).*)$",
        re.IGNORECASE,
    )
    _CANCEL_ID_RE = re.compile(r"^(?:取消|cancel)\s+(.+?)$", re.IGNORECASE)

    def __init__(self, sessions: TaskSessionStore) -> None:
        self.sessions = sessions

    def is_natural_action_text(self, text: str) -> bool:
        clean = " ".join(str(text or "").split())
        return bool(
            self._CONFIRM_RE.match(clean)
            or self._CANCEL_RE.match(clean)
            or self._CANCEL_ID_RE.match(clean)
            or self._RETRY_RE.match(clean)
        )

    async def handle_natural_action(
        self,
        *,
        text: str,
        event: Any,
        scope_id: str,
        actor_id: str,
        runtime: Any,
        composer: TaskResponseComposer,
        remote: RemoteTaskDelegator,
    ) -> NaturalTaskAction:
        clean = " ".join(str(text or "").split())
        cancel_id_match = self._CANCEL_ID_RE.match(clean)
        if not bool(runtime.config.get("assistant_task_natural_confirm", True)):
            return NaturalTaskAction(reason="natural_confirm_disabled")
        if not self.is_natural_action_text(clean):
            return NaturalTaskAction(reason="not_natural_pending_action")
        action_kind = (
            "cancel"
            if self._CANCEL_RE.match(clean) or cancel_id_match
            else "retry"
            if self._RETRY_RE.match(clean)
            else "confirm"
        )
        action_token = self.sessions.claim_action(scope_id, actor_id, action_kind)
        if not action_token:
            return NaturalTaskAction(
                True,
                "刚才的任务状态还在处理中，请稍后再试。",
                True,
                "natural_action_in_progress",
            )
        try:
            return await self._handle_claimed_action(
                clean=clean,
                cancel_id_match=cancel_id_match,
                action_token=action_token,
                event=event,
                scope_id=scope_id,
                actor_id=actor_id,
                runtime=runtime,
                composer=composer,
                remote=remote,
            )
        finally:
            self.sessions.release_action(scope_id, actor_id, action_token)

    async def _handle_claimed_action(
        self,
        *,
        clean: str,
        cancel_id_match: re.Match[str] | None,
        action_token: str,
        event: Any,
        scope_id: str,
        actor_id: str,
        runtime: Any,
        composer: TaskResponseComposer,
        remote: RemoteTaskDelegator,
    ) -> NaturalTaskAction:
        state = self.sessions.session(scope_id, actor_id)
        if self._CANCEL_RE.match(clean) or cancel_id_match:
            remote_action = await self._cancel_remote(
                runtime=runtime,
                event=event,
                scope_id=scope_id,
                actor_id=actor_id,
                remote=remote,
                request_id=cancel_id_match.group(1) if cancel_id_match else "",
            )
            if remote_action is not None:
                return remote_action
        if state.latest_remote_authorization_pending and self._CANCEL_RE.match(clean):
            contexts = getattr(runtime, "execution_context_registry", None)
            if contexts is not None and state.latest_execution_context_id:
                contexts.discard(state.latest_execution_context_id)
            state.latest_remote_authorization_pending = False
            state.latest_execution_context_id = ""
            self.sessions.persist(state)
            return NaturalTaskAction(
                True,
                "好，这次不转交执行端了。",
                True,
                "natural_cancel_remote_authorization",
            )
        if state.latest_remote_authorization_pending and self._CONFIRM_RE.match(clean):
            contexts = getattr(runtime, "execution_context_registry", None)
            execution_context = None
            if contexts is not None and state.latest_execution_context_id:
                execution_context = contexts.consume(
                    state.latest_execution_context_id,
                    scope_id=scope_id,
                    actor_id=actor_id,
                )
            original_task = execution_context.original_task if execution_context else state.latest_prompt
            capability = execution_context.capability if execution_context else state.latest_expected_capability
            lane = execution_context.lane if execution_context else state.latest_remote_lane
            reason = execution_context.reason if execution_context else state.latest_remote_reason
            constraints = {
                "authorization": "user_confirmed",
                "read_only": execution_context.read_only if execution_context else True,
                "source": "missing_local_integration",
                "suppress_notification": True,
            }
            turn_context = {
                "delivery_context": delivery_context_from_event(
                    event,
                    scope_id=scope_id,
                    actor_id=actor_id,
                ).to_dict()
            }
            result = remote.delegate(
                CodexDelegationRequest(
                    text=original_task,
                    scope_id=scope_id,
                    actor_id=actor_id,
                    capability=capability or "integration.recovery",
                    reason=reason or "missing_local_integration_authorized",
                    lane=lane or "interactive",
                    priority=25 if lane == "long" else 35,
                    expected_outputs=("final_summary", "evidence", "recovery_notes"),
                    turn_context=turn_context,
                    constraints=constraints,
                )
            )
            state.latest_remote_authorization_pending = False
            state.latest_execution_context_id = ""
            state.latest_remote_request_id = str(getattr(result, "request_id", "") or "")[:120]
            state.updated_at = __import__("time").time()
            self.sessions.persist(state)
            return NaturalTaskAction(
                True,
                composer.remote_delegate_reply(result),
                True,
                "natural_confirm_remote_authorization",
            )
        if self._RETRY_RE.match(clean):
            if state.latest_failure and state.latest_prompt:
                result = remote.delegate(
                    CodexDelegationRequest(
                        text=state.latest_prompt,
                        scope_id=scope_id,
                        actor_id=actor_id,
                        capability=state.latest_expected_capability,
                        reason="natural_retry_after_failure",
                        turn_context={
                            "delivery_context": delivery_context_from_event(
                                event,
                                scope_id=scope_id,
                                actor_id=actor_id,
                            ).to_dict()
                        },
                    )
                )
                return NaturalTaskAction(
                    True,
                    composer.remote_delegate_reply(result),
                    True,
                    "natural_retry_remote_delegate",
                )
        return NaturalTaskAction(
            True,
            "当前没有待确认的 Plana 任务。",
            True,
            "no_pending_operation",
        )
