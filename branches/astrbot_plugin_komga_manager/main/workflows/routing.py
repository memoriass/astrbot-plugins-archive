from __future__ import annotations

import re
from typing import Any

from .models import WorkflowRequest


def route_natural_text(text: str, params: dict[str, Any] | None = None) -> WorkflowRequest | None:
    raw = _clean(text)
    payload = dict(params or {})
    limit = _limit_from_text(raw) or payload.get("limit")
    if limit:
        payload["limit"] = limit

    if _has_write_intent(raw):
        workflow = _write_workflow(raw)
        target = _target_hint(raw)
        key = "series_id" if workflow == "refresh_series_metadata" else "library_id"
        if target:
            payload.setdefault(key, target)
        return WorkflowRequest(workflow, target=target, params=payload, source="tool")
    if any(token in raw for token in ("待继续", "继续阅读", "看到哪", "on deck", "ondeck")):
        return WorkflowRequest("on_deck", params=payload, source="tool")
    if any(token in raw for token in ("阅读列表", "书单", "readlist")):
        return WorkflowRequest("readlists", params=payload, source="tool")
    if any(token in raw for token in ("合集", "收藏集", "collection")):
        return WorkflowRequest("collections", params=payload, source="tool")
    if any(token in raw for token in ("最近", "新增", "更新了什么", "recent")):
        return WorkflowRequest("list_recent", params=payload, source="tool")
    if any(token in raw for token in ("书库", "漫画库", "library", "库列表")):
        return WorkflowRequest("list_libraries", params=payload, source="tool")
    series_id = str(payload.get("series_id") or _target_hint(raw)).strip()
    if series_id and any(token in raw for token in ("书籍", "章节", "卷", "books")):
        return WorkflowRequest("list_books", target=series_id, params=payload, source="tool")
    if series_id and any(token in raw for token in ("详情", "信息", "detail")):
        return WorkflowRequest("series_detail", target=series_id, params=payload, source="tool")
    if any(token in raw for token in ("详情", "系列信息", "series detail")):
        target = _target_hint(raw)
        return WorkflowRequest("series_detail", target=target, params=payload, source="tool")
    if any(token in raw for token in ("搜索", "查找", "找一下", "查一下", "漫画", "系列", "search")):
        query = _search_query(raw)
        return WorkflowRequest("search_series", target=query, params=payload, source="tool")
    return None


def _clean(text: str) -> str:
    cleaned = " ".join(str(text or "").casefold().split())
    cleaned = re.sub(r"^(?:plana|普拉娜|komga)\s*[,，:：]?\s*", "", cleaned)
    return cleaned.strip(" ，。！？,.!?")


def _has_write_intent(text: str) -> bool:
    return any(
        token in text
        for token in (
            "扫描",
            "扫库",
            "分析书库",
            "分析漫画库",
            "刷新元数据",
            "刷新书库元数据",
            "刷新系列元数据",
        )
    )


def _write_workflow(text: str) -> str:
    if re.search(r"(?:刷新.{0,8}系列元数据|系列元数据.{0,8}刷新)", text):
        return "refresh_series_metadata"
    if "刷新元数据" in text:
        return "refresh_library_metadata"
    if "分析" in text:
        return "analyze_library"
    return "scan_library"


def _search_query(text: str) -> str:
    cleaned = re.sub(
        r"(?:帮我|给我|请|看看|搜索|查找|找一下|查一下|漫画|系列|在|komga)",
        " ",
        text,
    )
    return " ".join(cleaned.split()).strip(" ，。！？,.!?")


def _target_hint(text: str) -> str:
    quoted = re.search(r"[\"'“”‘’]([^\"'“”‘’]{1,120})[\"'“”‘’]", text)
    if quoted:
        return quoted.group(1).strip()
    match = re.search(r"(?:id|ID)\s*[:：#]?\s*([A-Za-z0-9_-]{2,120})", text)
    return match.group(1) if match else ""


def _limit_from_text(text: str) -> int | None:
    match = re.search(r"(?:前|最近|列出|显示)?\s*(\d{1,3})\s*(?:条|本|个|项)?", text)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 100))
