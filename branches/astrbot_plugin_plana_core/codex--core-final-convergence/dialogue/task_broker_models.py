from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import DialogueDecision, TurnContext
from .wake import WakeDecision

@dataclass(slots=True)
class AssistantTaskRequest:
    event: Any
    text: str
    wake: WakeDecision
    decision: DialogueDecision
    turn_context: TurnContext
    preflight_source: str = ""
    preflight_reason: str = ""


@dataclass(slots=True)
class AssistantTaskResult:
    handled: bool = False
    reply: str = ""
    stop_event: bool = False
    reason: str = ""
    render_document: dict[str, Any] | None = None
