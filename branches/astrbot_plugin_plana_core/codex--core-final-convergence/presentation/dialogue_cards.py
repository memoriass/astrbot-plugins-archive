from __future__ import annotations

from typing import Any

from .search_results import recommendation_card_document


_RECOMMENDATION_ACTIONS = (
    "推荐", "选择", "吃什么", "看什么", "听什么", "玩什么",
    "recommend", "options",
)
_VISUAL_RECOMMENDATION_DOMAINS = (
    "早餐", "午餐", "晚餐", "宵夜", "夜宵", "吃", "菜", "食物", "料理",
    "番剧", "动漫", "动画", "电影", "电视剧", "漫画", "小说", "书", "音乐", "游戏",
)


def recommendation_document(
    query: str,
    response_text: str = "",
    *,
    search_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    _ = response_text
    return recommendation_card_document(query, search_result)


def should_render_recommendation_query(query: str) -> bool:
    clean = " ".join(str(query or "").strip().lower().split())
    if "卡片" in clean:
        return True
    return any(term in clean for term in _RECOMMENDATION_ACTIONS) and any(
        term in clean for term in _VISUAL_RECOMMENDATION_DOMAINS
    )


def is_artifact_resend_request(text: str) -> bool:
    clean = " ".join(str(text or "").strip().lower().split())
    object_term = any(term in clean for term in ("图", "图片", "卡片", "文件", "结果"))
    resend_term = any(term in clean for term in ("再发", "重发", "重新发", "没出来", "没收到", "发一次"))
    return object_term and resend_term
