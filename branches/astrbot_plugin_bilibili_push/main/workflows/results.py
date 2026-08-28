from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowCard:
    template_name: str
    templates: dict[str, Any]
    viewport: dict[str, int] = field(
        default_factory=lambda: {"width": 1000, "height": 800},
    )
    selector: str = ".card-board"


@dataclass(slots=True)
class WorkflowResult:
    text: str
    cards: list[WorkflowCard] = field(default_factory=list)
    display_text: str = ""
    task_id: str = ""
    card_intent: str = "user_action"

    def __str__(self) -> str:
        return self.text


def ensure_workflow_result(value: Any) -> WorkflowResult:
    if isinstance(value, WorkflowResult):
        return value
    return WorkflowResult(str(value))
