from __future__ import annotations

import weakref
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import CustomFilter

_ACTIVE_PLUGIN_REF: weakref.ReferenceType | None = None


def set_active_warehouse(plugin: Any) -> None:
    global _ACTIVE_PLUGIN_REF
    _ACTIVE_PLUGIN_REF = weakref.ref(plugin) if plugin is not None else None


def active_warehouse() -> Any:
    if _ACTIVE_PLUGIN_REF is None:
        return None
    return _ACTIVE_PLUGIN_REF()


class PlanaWarehousePassiveCaptureFilter(CustomFilter):
    """Capture raw evidence without activating AstrBot's handler pipeline."""

    def filter(self, event: AstrMessageEvent, cfg: Any) -> bool:
        plugin = active_warehouse()
        if plugin is None:
            return False
        plugin._capture_message(event)
        return False
