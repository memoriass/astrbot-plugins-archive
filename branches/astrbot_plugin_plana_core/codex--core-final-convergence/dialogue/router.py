from __future__ import annotations

from typing import Any

from .analyzer import DialogueTurnAnalyzer
from .delivery import delivery_context_from_event
from .models import DialogueDecision, TurnContext
from .wake import WakeDecision


class DialogueRouter:
    """Classify AstrBot turns into local, controlled dialogue routes."""

    def __init__(self, analyzer: DialogueTurnAnalyzer | None = None) -> None:
        self.analyzer = analyzer or DialogueTurnAnalyzer()

    def turn_context(self, runtime: Any, event: Any) -> TurnContext:
        context, _decision = self.decision_for_event(runtime, event)
        return context

    def decision_for_event(
        self,
        runtime: Any,
        event: Any,
        wake: WakeDecision | None = None,
    ) -> tuple[TurnContext, DialogueDecision]:
        text = event.get_message_str().strip()
        message_type = event.get_message_type()
        source = wake.source if wake is not None else self._source(event)
        normalized_type = str(getattr(message_type, "value", message_type))
        is_wake = (
            wake.is_wake
            if wake is not None
            else bool(getattr(event, "is_wake", False))
        )
        decision = self.decide(
            text,
            source,
            message_type=normalized_type,
            is_wake=is_wake,
        )
        scope_id = runtime.resolve_scope(event.unified_msg_origin)
        actor_id = self._actor_id(runtime, event)
        return TurnContext(
            scope_id=scope_id,
            actor_id=actor_id,
            source=source,
            text=text,
            route=decision.route,
            intent=decision.intent,
            reason=decision.reason,
            proposal_source=decision.proposal_source,
            is_wake=is_wake,
            wake_state=wake.state if wake is not None else "",
            wake_reason=wake.reason if wake is not None else "",
            message_type=normalized_type,
            delivery_context=delivery_context_from_event(
                event,
                scope_id=scope_id,
                actor_id=actor_id,
            ).to_dict(),
        ), decision

    def decide(
        self,
        text: str,
        source: str = "astrbot_message",
        *,
        message_type: str = "",
        is_wake: bool = False,
    ) -> DialogueDecision:
        return self.analyzer.analyze(
            text,
            source,
            message_type=message_type,
            is_wake=is_wake,
        )

    def decision_for_action(
        self,
        action_name: str,
        text: str,
        *,
        reason: str = "",
    ) -> DialogueDecision | None:
        return self.analyzer.decision_for_action(action_name, text, reason=reason)

    def _source(self, event: Any) -> str:
        if getattr(event, "is_wake", False):
            return "astrbot_wake"
        if getattr(event, "is_at_or_wake_command", False):
            return "astrbot_at_or_wake"
        return "astrbot_message"

    def _actor_id(self, runtime: Any, event: Any) -> str:
        identity_from_event = getattr(runtime, "identity_from_event", None)
        if callable(identity_from_event):
            try:
                identity = identity_from_event(event)
                global_user_id = str(getattr(identity, "global_user_id", "") or "")
                if global_user_id:
                    return global_user_id
            except Exception:  # noqa: BLE001
                pass
        try:
            sender_id = str(event.get_sender_id() or "")
        except Exception:  # noqa: BLE001
            return ""
        if not sender_id:
            return ""
        platform = self._event_platform(event)
        return f"{platform}:{sender_id}" if platform else sender_id

    def _event_platform(self, event: Any) -> str:
        getter = getattr(event, "get_platform_name", None)
        if not callable(getter):
            return ""
        try:
            return str(getter() or "").strip()
        except Exception:  # noqa: BLE001
            return ""
