from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DialogueRoute = Literal[
    "inject_prompt",
    "codex_candidate",
    "memory_write",
    "read_direct",
    "status_query",
    "reject",
]
TurnIntent = Literal[
    "chat",
    "conversation_history",
    "memory_query",
    "profile_query",
    "context_preview",
    "memory_write",
    "tool_execution_candidate",
    "status_query",
    "unsupported_destructive",
]


@dataclass(frozen=True, slots=True)
class TurnContext:
    scope_id: str
    actor_id: str
    source: str
    text: str
    route: DialogueRoute
    intent: TurnIntent = "chat"
    reason: str = ""
    proposal_source: str = ""
    is_wake: bool = False
    wake_state: str = ""
    wake_reason: str = ""
    message_type: str = ""
    delivery_context: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "scope_id": self.scope_id,
            "actor_id": self.actor_id,
            "source": self.source,
            "text": self.text[:800],
            "route": self.route,
            "intent": self.intent,
            "reason": self.reason,
            "proposal_source": self.proposal_source,
            "is_wake": self.is_wake,
            "wake_state": self.wake_state,
            "wake_reason": self.wake_reason,
            "message_type": self.message_type,
            "delivery_context": dict(self.delivery_context),
        }


@dataclass(frozen=True, slots=True)
class DialogueDecision:
    route: DialogueRoute
    should_inject_prompt: bool = False
    codex_candidate: bool = False
    intent: TurnIntent = "chat"
    intent_text: str = ""
    proposal_source: str = ""
    should_stop_event: bool = False
    user_message: str = ""
    reason: str = ""
