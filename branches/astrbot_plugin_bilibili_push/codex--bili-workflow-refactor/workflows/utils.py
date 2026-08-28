from __future__ import annotations

import json
import re
from typing import Any

from .models import WORKFLOW_ALIASES


def normalize_workflow(value: str) -> str:
    key = str(value or "").strip()
    return WORKFLOW_ALIASES.get(key, WORKFLOW_ALIASES.get(key.lower(), key))


def parse_params(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"query": text}
        return dict(parsed) if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def first_text(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_sub_type(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"live", "直播", "l"}:
        return "live"
    if text in {"both", "all", "全部", "动态+直播", "dynamic+live"}:
        return "both"
    return "dynamic"


def normalize_reply(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def is_uid(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2,20}", str(value or "").strip()))
