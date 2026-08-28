from __future__ import annotations

import json
from typing import Any

from .models import WORKFLOW_ALIASES

def normalize_reply(raw: str) -> str:
    return "".join(str(raw or "").strip().lower().split())

def _looks_like_rss_url(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(("http://", "https://")) and ("rss" in text or "feed" in text)

def _looks_like_mikan_url(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(("http://", "https://")) and "mikan" in text and "/bangumi/" in text

def _canonical_key(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")

def _normalize_workflow(value: str) -> str:
    key = _canonical_key(value)
    return WORKFLOW_ALIASES.get(key, key)

def _split_words(value: str) -> list[str]:
    return [part for part in str(value or "").split() if part]

def _parse_kv_words(value: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for token in _split_words(value):
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        key = key.strip()
        if key:
            payload[key] = raw.strip()
    return payload

def _parse_params(params: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(params, dict):
        return dict(params)
    if not params:
        return {}
    text = str(params).strip()
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        parsed = _parse_kv_words(text)
        if parsed:
            parsed["_raw"] = text
            return parsed
        return {"_raw": text}
    return payload if isinstance(payload, dict) else {}

def _first_text(params: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def _get_bool(params: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = params.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "启用", "是"}:
        return True
    if text in {"0", "false", "no", "n", "off", "禁用", "否"}:
        return False
    return default

def _get_optional_bool(params: dict[str, Any], key: str) -> bool | None:
    if key not in params:
        return None
    return _get_bool(params, key)

def _get_int(params: dict[str, Any], key: str, *, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default

def _get_float(params: dict[str, Any], key: str, *, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default

def _score_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def _format_score(value: Any) -> str:
    score = _score_value(value)
    return "-" if score <= 0 else f"{score:.1f}"

def _normalize_season(value: str) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "spring": "春",
        "spr": "春",
        "1": "春",
        "q1": "春",
        "春": "春",
        "夏": "夏",
        "summer": "夏",
        "sum": "夏",
        "2": "夏",
        "q2": "夏",
        "秋": "秋",
        "autumn": "秋",
        "fall": "秋",
        "3": "秋",
        "q3": "秋",
        "冬": "冬",
        "winter": "冬",
        "win": "冬",
        "4": "冬",
        "q4": "冬",
    }
    return mapping.get(text, "")

def _season_label(season: dict[str, Any]) -> str:
    year = season.get("year")
    season_name = season.get("season")
    if year and season_name:
        return f"{year} {season_name}"
    return ""
