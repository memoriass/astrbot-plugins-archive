from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NaturalTaskAction:
    handled: bool = False
    reply: str = ""
    stop_event: bool = False
    reason: str = ""
    render_document: dict[str, Any] | None = None
