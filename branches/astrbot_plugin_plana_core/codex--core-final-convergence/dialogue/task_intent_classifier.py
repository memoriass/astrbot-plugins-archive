from __future__ import annotations

from typing import Any

from .capability_broker import CapabilityBroker, CapabilityDecision


class TaskIntentClassifier:
    """Maps a routed dialogue intent to a bounded Core capability view."""

    def __init__(self, capabilities: CapabilityBroker | None = None) -> None:
        self.capabilities = capabilities or CapabilityBroker()

    def classify(self, runtime: Any, text: str, intent: str) -> CapabilityDecision:
        return self.capabilities.decide(runtime, text, intent)
