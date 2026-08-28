from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.intent_patterns import (
    looks_like_explicit_codex_request,
    looks_like_long_task_request,
    native_tool_profile,
)


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    capability: str
    route: str
    reason: str = ""
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityBroker:
    """Select either one AstrBot tool profile or governed Codex execution."""

    def decide(self, runtime: Any, text: str, intent: str) -> CapabilityDecision:
        clean = " ".join(str(text or "").split())[:800]
        native_mode = bool(runtime.config.get("assistant_native_tool_mode", True))
        try:
            long_threshold = int(runtime.config.get("assistant_long_task_threshold_seconds", 120))
        except (TypeError, ValueError):
            long_threshold = 120
        long_task = looks_like_long_task_request(
            clean,
            threshold_seconds=max(1, long_threshold),
        )
        explicit_codex = looks_like_explicit_codex_request(clean)
        if intent != "tool_execution_candidate":
            return CapabilityDecision(
                capability="",
                route="unavailable",
                reason="not_execution_intent",
                available=False,
            )
        if native_mode and not explicit_codex and not long_task:
            profile = native_tool_profile(clean)
            if profile:
                return CapabilityDecision(
                    capability=f"native.{profile}",
                    route="astr_llm_tool",
                    reason=f"native_tool_profile:{profile}",
                    metadata={
                        "tool_profile": profile,
                        "risk_class": "low_risk_request_scoped",
                    },
                )
        lane = "long" if long_task else "interactive"
        return CapabilityDecision(
            capability="codex.long_task" if lane == "long" else "codex.interactive",
            route="remote_runner",
            reason="long_task" if long_task else "controlled_external_execution",
            metadata={
                "codex_lane": lane,
                "risk_class": "delegated_long_task" if long_task else "delegated_interactive",
            },
        )
