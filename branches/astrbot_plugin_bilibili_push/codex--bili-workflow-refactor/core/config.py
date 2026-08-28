from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PluginConfig:
    push_on_startup: bool = False
    check_interval: int = 30
    dynamic_check_interval: int = 120
    live_check_interval: int = 30
    request_delay_sec: float = 0.8
    request_jitter_sec: float = 5.0
    live_batch_size: int = 50
    risk_cooldown_sec: int = 1800
    enable_link_parser: bool = True
    search_cache_expiry_hours: int = 24
    enable_ai_tools: bool = True
    ai_pending_timeout_sec: int = 300
    enable_ai_auto_select_candidates: bool = True
    ai_auto_select_confidence: float = 0.88
    verify_ssl: bool = True


def load_plugin_config(raw: dict | None) -> PluginConfig:
    raw = raw or {}
    check_interval = safe_int(raw.get("check_interval"), 30, min_value=5)
    return PluginConfig(
        push_on_startup=safe_bool(raw.get("push_on_startup"), False),
        check_interval=check_interval,
        dynamic_check_interval=safe_int(
            raw.get("dynamic_check_interval"),
            max(check_interval, 120),
            min_value=30,
        ),
        live_check_interval=safe_int(
            raw.get("live_check_interval"),
            check_interval,
            min_value=5,
        ),
        request_delay_sec=safe_float(
            raw.get("request_delay_sec"),
            0.8,
            min_value=0.0,
            max_value=30.0,
        ),
        request_jitter_sec=safe_float(
            raw.get("request_jitter_sec"),
            5.0,
            min_value=0.0,
            max_value=120.0,
        ),
        live_batch_size=safe_int(
            raw.get("live_batch_size"),
            50,
            min_value=1,
            max_value=100,
        ),
        risk_cooldown_sec=safe_int(
            raw.get("risk_cooldown_sec"),
            1800,
            min_value=60,
        ),
        enable_link_parser=safe_bool(raw.get("enable_link_parser"), True),
        search_cache_expiry_hours=safe_int(
            raw.get("search_cache_expiry_hours"),
            24,
            min_value=1,
        ),
        enable_ai_tools=safe_bool(raw.get("enable_ai_tools"), True),
        ai_pending_timeout_sec=safe_int(
            raw.get("ai_pending_timeout_sec"),
            300,
            min_value=30,
        ),
        enable_ai_auto_select_candidates=safe_bool(
            raw.get("enable_ai_auto_select_candidates"),
            True,
        ),
        ai_auto_select_confidence=safe_float(
            raw.get("ai_auto_select_confidence"),
            0.88,
            min_value=0.0,
            max_value=1.0,
        ),
        verify_ssl=safe_bool(raw.get("verify_ssl"), True),
    )


def safe_int(
    value: Any,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    try:
        if value is None or value == "":
            result = int(default)
        else:
            result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return _clamp(result, min_value, max_value)


def safe_float(
    value: Any,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    try:
        if value is None or value == "":
            result = float(default)
        else:
            result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return _clamp(result, min_value, max_value)


def safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "启用", "开启", "有效"}:
        return True
    if text in {"0", "false", "no", "off", "禁用", "关闭", "无效"}:
        return False
    return default


def _clamp(value, min_value, max_value):
    if min_value is not None and value < min_value:
        return min_value
    if max_value is not None and value > max_value:
        return max_value
    return value
