from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .formatting import format_ani_summary


async def find_enabled_duplicate_subscription(
    plugin: Any,
    ani: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        fetch = getattr(plugin, "cached_list_ani", None)
        existing_items = await fetch() if callable(fetch) else await plugin.client(require_api_key=True).list_ani()
    except Exception:
        return None

    for existing in existing_items:
        if not isinstance(existing, dict) or not existing.get("enable"):
            continue
        if _same_rss(existing, ani) or _same_bgm_and_subgroup(existing, ani):
            return existing
    return None


def format_duplicate_subscription(duplicate: dict[str, Any]) -> str:
    return "ANI-RSS 已存在启用订阅，本次不重复添加:\n" + format_ani_summary(duplicate)


def _same_rss(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_url = _normalize_url(str(left.get("url") or ""))
    right_url = _normalize_url(str(right.get("url") or ""))
    return bool(left_url and right_url and left_url == right_url)


def _same_bgm_and_subgroup(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_bgm = _normalize_url(str(left.get("bgmUrl") or ""))
    right_bgm = _normalize_url(str(right.get("bgmUrl") or ""))
    if not left_bgm or not right_bgm or left_bgm != right_bgm:
        return False
    left_group = str(left.get("subgroup") or "").strip()
    right_group = str(right.get("subgroup") or "").strip()
    return not left_group or not right_group or left_group == right_group


def _normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/").lower()
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = parsed.query.strip()
    return urlunsplit((scheme, netloc, path, query, ""))
