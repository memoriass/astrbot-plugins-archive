from __future__ import annotations

import time
from typing import Any


CONFIG_KEYS = (
    "enabled",
    "enable_core_api",
    "max_content_chars",
    "max_search_limit",
    "max_bulk_items",
    "allow_commands",
    "capture_messages",
    "capture_llm_responses",
    "capture_commands",
    "excluded_prefixes",
    "min_content_chars",
    "retention_days",
    "maintenance_on_start",
)


def normalize_config(config: Any) -> dict[str, Any]:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return {}
    return {key: getter(key) for key in CONFIG_KEYS if getter(key) is not None}


def bounded_int(value: object, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def prefixes(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = str(value or "").split(",")
    return tuple(str(item).strip() for item in raw_items if str(item).strip())


def prune_before_ts(payload: dict[str, Any]) -> int:
    if payload.get("before_ts") not in {None, ""}:
        return bounded_int(payload.get("before_ts"), 0, minimum=0, maximum=2**31 - 1)
    days = bounded_int(payload.get("retention_days"), 0, minimum=0, maximum=3650)
    if days <= 0:
        return 0
    return int(time.time()) - days * 86_400
