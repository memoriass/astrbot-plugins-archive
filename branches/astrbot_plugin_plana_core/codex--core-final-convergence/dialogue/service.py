from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

try:
    from astrbot.api import logger
except ModuleNotFoundError:  # pragma: no cover - standalone checks
    import logging

    logger = logging.getLogger(__name__)

from .context_policy import CONTROLLED_TOOL_ROUTE_PREFIX, DialogueContextPolicy
from .behavior import BehaviorOrchestrator
from .direct_reads import DialogueDirectReads
from .ledger import DialogueLedger
from .observer import DialogueObserver
from .preflight import DialogueResponsePreflight
from .router import DialogueRouter
from .task_broker import AssistantTaskBroker, AssistantTaskRequest
from .tool_policy import (
    attach_intent_tools,
    intent_chat_tool_names,
    restrict_default_chat_tools,
    tool_profile_for_text,
)
from .wake import DialogueWakeStateMachine
from .social_state import SocialInteractionStore
from .response_style import review_response_style
from .service_support import DialogueServiceSupportMixin

@dataclass(frozen=True, slots=True)
class DialogueDispatchResult:
    reply: str = ""
    stop_event: bool = False
    reason: str = ""
    render_document: dict[str, Any] | None = None


class DialogueService(DialogueServiceSupportMixin):
    """Framework-local dialogue core for normal AstrBot conversation turns."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.router = DialogueRouter()
        self.wake_state = DialogueWakeStateMachine()
        self.behavior = BehaviorOrchestrator()
        self.ledger = DialogueLedger.from_config(runtime.config)
        setattr(self.runtime, "dialogue_ledger", self.ledger)
        self.context_policy = DialogueContextPolicy()
        self.direct_reads = DialogueDirectReads()
        self.observer = DialogueObserver()
        self.preflight = DialogueResponsePreflight()
        self.task_broker = AssistantTaskBroker(runtime)
        database = getattr(getattr(runtime, "storage", None), "db", None)
        self.social_states = SocialInteractionStore(database)

    async def stop(self) -> None:
        await self.observer.stop()

    def has_pending_task_action(self, event: Any, text: str) -> bool:
        session_service = self.task_broker.session_service
        if not session_service.is_natural_action_text(text):
            return False
        scope_id, actor_id = self._conversation_identity(event)
        state = self.task_broker.sessions.session(scope_id, actor_id)
        return bool(state.latest_remote_authorization_pending)

    def observe_message(self, event: Any) -> None:
        self.ledger.ingest_event(self.runtime, event)
        self.observer.ingest_event(self.runtime, event)
        scope_id, actor_id = self._conversation_identity(event)
        self.social_states.record_feedback(scope_id, actor_id, event.get_message_str())

    def should_consider_event(self, event: Any) -> bool:
        """Return whether a passive group turn is a conservative opportunity."""
        if not bool(self.runtime.config.get("assistant_behavior_orchestrator", True)):
            return False
        wake = self._wake_decision(event)
        if (
            self._is_group_event(event)
            and wake.state == "observation"
            and not wake.should_dispatch
        ):
            return False
        scope_id, actor_id = self._conversation_identity(event)
        behavior = self.behavior.decide(
            self.runtime,
            event,
            wake,
            social_state=self.social_states.get(scope_id, actor_id),
            session_state=self.task_broker.sessions.session(scope_id, actor_id),
        )
        setattr(event, "_plana_behavior_decision", behavior)
        return behavior.action != "silence"

    async def dispatch_message(self, event: Any, provider: Any) -> str:
        """Optionally dispatch natural-language turns into governed routes."""
        outcome = await self.dispatch_event(event, provider)
        return outcome.reply

    async def dispatch_event(self, event: Any, provider: Any) -> DialogueDispatchResult:
        """Dispatch one message and report whether downstream handlers should stop."""
        if not self._auto_turn_analysis_enabled():
            return DialogueDispatchResult()
        wake = self._wake_decision(event)
        if wake.direct_reply:
            self._record_direct_response(event, wake.direct_reply)
            return DialogueDispatchResult(wake.direct_reply, True, wake.reason)
        text = event.get_message_str().strip()
        command_like = self._looks_like_plana_command(text)
        if not text or text.startswith("/") or command_like:
            return DialogueDispatchResult()
        scope_id, actor_id = self._conversation_identity(event)
        behavior = getattr(event, "_plana_behavior_decision", None)
        if behavior is None:
            behavior = self.behavior.decide(
                self.runtime,
                event,
                wake,
                social_state=self.social_states.get(scope_id, actor_id),
                session_state=self.task_broker.sessions.session(scope_id, actor_id),
            )
            setattr(event, "_plana_behavior_decision", behavior)
        if behavior.action == "silence":
            return DialogueDispatchResult(reason=behavior.participation_reason)
        if behavior.action == "reject":
            reply = "这个目标属于禁止操作，我不会执行。可以改为只读检查或提供安全的恢复方案。"
            self._record_direct_response(event, reply)
            return DialogueDispatchResult(reply, True, behavior.participation_reason)
        setattr(event, "_plana_media_intent", behavior.media_intent)
        self.task_broker.sessions.push_focus(
            scope_id,
            actor_id,
            topic=text,
            capability=behavior.capability,
            resource_refs=behavior.delivery_context.get("resource_refs", []),
            task_id=str(behavior.delivery_context.get("task_id") or ""),
        )
        turn_context, decision = self.router.decision_for_event(
            self.runtime,
            event,
            wake,
        )
        if behavior.capability == "model_only" and decision.intent == "tool_execution_candidate":
            decision = replace(
                decision,
                route="inject_prompt",
                intent="chat",
                codex_candidate=False,
                should_stop_event=False,
                reason="behavior_model_only_override",
            )
            turn_context = replace(
                turn_context,
                route="inject_prompt",
                intent="chat",
                reason="behavior_model_only_override",
            )
        elif behavior.action == "codex" and decision.intent != "tool_execution_candidate":
            decision = replace(
                decision,
                route="codex_candidate",
                intent="tool_execution_candidate",
                codex_candidate=True,
                should_stop_event=True,
                reason="behavior_codex_override",
            )
            turn_context = replace(
                turn_context,
                route="codex_candidate",
                intent="tool_execution_candidate",
                reason="behavior_codex_override",
            )
        elif behavior.action == "cancel_or_correct" and decision.intent != "tool_execution_candidate":
            decision = replace(
                decision,
                route="codex_candidate",
                intent="tool_execution_candidate",
                codex_candidate=True,
                should_stop_event=True,
                reason="behavior_cancel_or_correct_override",
            )
            turn_context = replace(
                turn_context,
                route="codex_candidate",
                intent="tool_execution_candidate",
                reason="behavior_cancel_or_correct_override",
            )
        should_dispatch = self._should_dispatch_event(event, wake)
        if not should_dispatch and wake.source != "plana_name_mention":
            return DialogueDispatchResult()
        if behavior.action == "codex":
            task_result = await self.task_broker.handle(
                AssistantTaskRequest(
                    event=event,
                    text=text,
                    wake=wake,
                    decision=decision,
                    turn_context=turn_context,
                    preflight_source="local_behavior",
                    preflight_reason="deterministic_codex_route",
                ),
                provider,
            )
            if task_result.handled:
                if task_result.reply:
                    self._record_direct_response(event, task_result.reply)
                return DialogueDispatchResult(
                    task_result.reply,
                    task_result.stop_event,
                    task_result.reason,
                    task_result.render_document,
                )
        preflight = await self._preflight_allows(
            event,
            text,
            wake,
            decision,
            provider,
        )
        if not preflight.should_respond:
            setattr(event, "_plana_preflight_accepted", False)
            return DialogueDispatchResult(
                "",
                False,
                preflight.reason,
            )
        setattr(event, "_plana_preflight_accepted", True)
        turn_context, decision = self._apply_preflight_intent(
            text,
            turn_context,
            decision,
            preflight,
        )
        if behavior.action == "codex" and decision.intent != "tool_execution_candidate":
            decision = replace(
                decision,
                route="codex_candidate",
                intent="tool_execution_candidate",
                codex_candidate=True,
                should_stop_event=True,
                reason="behavior_codex_post_preflight_override",
            )
            turn_context = replace(
                turn_context,
                route="codex_candidate",
                intent="tool_execution_candidate",
                reason="behavior_codex_post_preflight_override",
            )
        if decision.route == "inject_prompt" and wake.source == "plana_name_mention":
            setattr(event, "is_at_or_wake_command", True)
        if decision.route == "reject":
            self._record_direct_response(event, decision.user_message)
            return DialogueDispatchResult(
                decision.user_message,
                bool(decision.should_stop_event),
                decision.reason,
            )
        if decision.route == "status_query":
            reply = self._user_status_text()
            self._record_direct_response(event, reply)
            return DialogueDispatchResult(reply, True, decision.reason)
        if decision.route == "memory_write":
            reply = self._remember_basic_text(event, text)
            self._record_direct_response(event, reply)
            return DialogueDispatchResult(reply, True, decision.reason)
        if decision.route == "read_direct":
            reply = await self.direct_reads.reply_for(
                self.runtime,
                event,
                text,
                decision.intent,
            )
            if reply:
                self._record_direct_response(event, reply)
                return DialogueDispatchResult(reply, True, decision.reason)
            return DialogueDispatchResult(reason=decision.reason)
        task_result = await self.task_broker.handle(
            AssistantTaskRequest(
                event=event,
                text=text,
                wake=wake,
                decision=decision,
                turn_context=turn_context,
                preflight_source=preflight.source,
                preflight_reason=preflight.reason,
            ),
            provider,
        )
        if task_result.handled:
            if task_result.reply:
                self._record_direct_response(event, task_result.reply)
            return DialogueDispatchResult(
                task_result.reply,
                task_result.stop_event,
                task_result.reason,
                task_result.render_document,
            )
        return DialogueDispatchResult(reason=decision.reason)

    async def inject_prompt(self, event: Any, request_obj: Any, provider: Any) -> None:
        wake = self._wake_decision(event)
        if not self._should_dispatch_event(event, wake):
            return
        _context, decision = self.router.decision_for_event(self.runtime, event, wake)
        scope_id, actor_id = self._conversation_identity(event)
        behavior = getattr(event, "_plana_behavior_decision", None)
        if behavior is None:
            behavior = self.behavior.decide(
                self.runtime,
                event,
                wake,
                social_state=self.social_states.get(scope_id, actor_id),
                session_state=self.task_broker.sessions.session(scope_id, actor_id),
            )
            setattr(event, "_plana_behavior_decision", behavior)
        attach_intent_tools(
            request_obj,
            event.get_message_str().strip(),
            getattr(self.runtime, "astr_context", None),
        )
        selected_tool_profile = (
            str(getattr(event, "_plana_native_tool_profile", "") or "")
            or tool_profile_for_text(event.get_message_str().strip())
            or ("memory" if decision.intent == "memory_query" else "")
        )
        restrict_default_chat_tools(
            request_obj,
            self.runtime.config,
            event.get_message_str().strip(),
            profile=selected_tool_profile,
            astr_context=getattr(self.runtime, "astr_context", None),
        )
        if not decision.should_inject_prompt and not intent_chat_tool_names(
            event.get_message_str().strip()
        ):
            return
        preflight = await self._preflight_allows(
            event,
            event.get_message_str().strip(),
            wake,
            decision,
            provider,
        )
        if not preflight.should_respond:
            setattr(event, "_plana_preflight_accepted", False)
            return
        prompt_block = await self.context_policy.build_prompt_block(
            self.runtime,
            event,
            provider,
            behavior=behavior,
            tool_profile=selected_tool_profile,
        )
        if not prompt_block:
            prompt_block = ""
        behavior_prompt = self.behavior.prompt_block(
            behavior,
            self.social_states.get(scope_id, actor_id),
        )
        anchor_prompt = self._message_anchor_prompt(event)
        prompt_block = f"{prompt_block}\n{behavior_prompt}\n{anchor_prompt}".strip()
        if prompt_block.startswith(CONTROLLED_TOOL_ROUTE_PREFIX):
            base_prompt = getattr(request_obj, "system_prompt", "") or ""
            request_obj.system_prompt = f"{base_prompt}\n{prompt_block}".strip()
            return
        if self._append_temp_user_context(request_obj, prompt_block):
            return
        base_prompt = getattr(request_obj, "system_prompt", "") or ""
        request_obj.system_prompt = f"{base_prompt}\n{prompt_block}".strip()

    async def observe_response(self, event: Any, response: Any, provider: Any) -> None:
        text = str(getattr(response, "completion_text", "") or "")
        self.ledger.ingest_response(self.runtime, event, text)
        self.wake_state.observe_response(self.runtime, event, replied=bool(text.strip()))
        self.task_broker.observe_model_response(event, text)
        style_review = review_response_style(text)
        setattr(event, "_plana_response_style_review", style_review.to_dict())
        if not style_review.natural:
            logger.info(
                "Plana response style review: mechanical=%s formal=%s addresses=%s follow_up=%s",
                style_review.mechanical_markers,
                style_review.formal_count,
                style_review.address_count,
                style_review.asks_unnecessary_follow_up,
            )
        scope_id, actor_id = self._conversation_identity(event)
        failed = any(marker in text.lower() for marker in ("失败", "错误", "无法", "超时", "error", "failed"))
        if text.strip():
            self.social_states.record_outcome(scope_id, actor_id, success=not failed)
        await self.observer.record_response(self.runtime, event, response, provider)
