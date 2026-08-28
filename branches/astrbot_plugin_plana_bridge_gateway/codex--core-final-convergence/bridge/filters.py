from __future__ import annotations

import weakref
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import CustomFilter

_ACTIVE_PLUGIN_REF: weakref.ReferenceType | None = None


def set_active_bridge_gateway(plugin: Any) -> None:
    global _ACTIVE_PLUGIN_REF
    _ACTIVE_PLUGIN_REF = weakref.ref(plugin) if plugin is not None else None


def active_bridge_gateway() -> Any:
    if _ACTIVE_PLUGIN_REF is None:
        return None
    return _ACTIVE_PLUGIN_REF()


class PlanaBridgeForwardFilter(CustomFilter):
    """Activate Bridge only when forwarding is explicitly enabled."""

    def filter(self, event: AstrMessageEvent, cfg: Any) -> bool:
        plugin = active_bridge_gateway()
        if plugin is None:
            return False
        return bool(plugin._should_forward_event(event))
