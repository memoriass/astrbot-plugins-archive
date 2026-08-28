from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from ..utils.timezone import normalize_display_timezone
except ImportError:
    from utils.timezone import normalize_display_timezone


@dataclass(slots=True)
class PluginConfig:
    display_timezone: str = "Asia/Shanghai"
    push_on_startup: bool = False
    check_interval: int = 60
    dynamic_check_interval: int = 300
    live_check_interval: int = 90
    request_delay_sec: float = 1.5
    request_jitter_sec: float = 30.0
    live_batch_size: int = 50
    risk_cooldown_sec: int = 3600
    enable_link_parser: bool = True
    enable_parser_video_download: bool = False
    parser_video_max_size_mb: int = 30
    parser_video_download_timeout_sec: int = 30
    search_cache_expiry_hours: int = 48
    enable_ai_tools: bool = True
    ai_pending_timeout_sec: int = 300
    enable_ai_semantic_dispatch: bool = True
    ai_semantic_dispatch_confidence: float = 0.82
    ai_semantic_dispatch_timeout_sec: float = 8.0
    enable_ai_candidate_analysis: bool = True
    ai_candidate_analysis_confidence: float = 0.86
    ai_candidate_analysis_timeout_sec: float = 8.0
    enable_ai_auto_select_candidates: bool = True
    ai_auto_select_confidence: float = 0.88
    verify_ssl: bool = True


def load_plugin_config(raw: dict | None) -> PluginConfig:
    raw = raw or {}
    check_interval = safe_int(raw.get("check_interval"), 60, min_value=5)
    return PluginConfig(
        display_timezone=normalize_display_timezone(raw.get("display_timezone")),
        push_on_startup=safe_bool(raw.get("push_on_startup"), False),
        check_interval=check_interval,
        dynamic_check_interval=safe_int(
            raw.get("dynamic_check_interval"),
            max(check_interval, 300),
            min_value=30,
        ),
        live_check_interval=safe_int(
            raw.get("live_check_interval"),
            max(check_interval, 90),
            min_value=5,
        ),
        request_delay_sec=safe_float(
            raw.get("request_delay_sec"),
            1.5,
            min_value=0.0,
            max_value=30.0,
        ),
        request_jitter_sec=safe_float(
            raw.get("request_jitter_sec"),
            30.0,
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
            3600,
            min_value=60,
        ),
        enable_link_parser=safe_bool(raw.get("enable_link_parser"), True),
        enable_parser_video_download=safe_bool(
            raw.get("enable_parser_video_download"),
            False,
        ),
        parser_video_max_size_mb=safe_int(
            raw.get("parser_video_max_size_mb"),
            30,
            min_value=1,
            max_value=200,
        ),
        parser_video_download_timeout_sec=safe_int(
            raw.get("parser_video_download_timeout_sec"),
            30,
            min_value=5,
            max_value=300,
        ),
        search_cache_expiry_hours=safe_int(
            raw.get("search_cache_expiry_hours"),
            48,
            min_value=1,
        ),
        enable_ai_tools=safe_bool(raw.get("enable_ai_tools"), True),
        ai_pending_timeout_sec=safe_int(
            raw.get("ai_pending_timeout_sec"),
            300,
            min_value=30,
        ),
        enable_ai_semantic_dispatch=safe_bool(
            raw.get("enable_ai_semantic_dispatch"),
            True,
        ),
        ai_semantic_dispatch_confidence=safe_float(
            raw.get("ai_semantic_dispatch_confidence"),
            0.82,
            min_value=0.0,
            max_value=1.0,
        ),
        ai_semantic_dispatch_timeout_sec=safe_float(
            raw.get("ai_semantic_dispatch_timeout_sec"),
            8.0,
            min_value=1.0,
            max_value=30.0,
        ),
        enable_ai_candidate_analysis=safe_bool(
            raw.get("enable_ai_candidate_analysis"),
            True,
        ),
        ai_candidate_analysis_confidence=safe_float(
            raw.get("ai_candidate_analysis_confidence"),
            0.86,
            min_value=0.0,
            max_value=1.0,
        ),
        ai_candidate_analysis_timeout_sec=safe_float(
            raw.get("ai_candidate_analysis_timeout_sec"),
            8.0,
            min_value=1.0,
            max_value=30.0,
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
