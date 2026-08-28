from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .capability_broker import CapabilityDecision


@dataclass(frozen=True, slots=True)
class TaskRouteDecision:
    action: str
    capability: str
    reason: str
    stop_event: bool = True
    remote_reason: str = ""
    lane: str = "interactive"
    priority: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)


class TaskRouteDecider:
    """Keep execution routing to one request-scoped tool or Codex."""

    def decide(
        self,
        runtime: Any,
        text: str,
        capability: CapabilityDecision,
    ) -> TaskRouteDecision:
        del runtime, text
        if capability.route == "astr_llm_tool":
            return TaskRouteDecision(
                action="handoff_llm_tool",
                capability=capability.capability,
                reason=capability.reason,
                stop_event=False,
                metadata=capability.metadata,
            )
        lane = str(capability.metadata.get("codex_lane") or "interactive")
        return TaskRouteDecision(
            action="remote_delegate",
            capability=capability.capability or ("codex.long_task" if lane == "long" else "codex.interactive"),
            reason=capability.reason or "controlled_external_execution",
            remote_reason=capability.reason or "controlled_external_execution",
            lane=lane,
            priority=25 if lane == "long" else 35,
            metadata=capability.metadata,
        )
