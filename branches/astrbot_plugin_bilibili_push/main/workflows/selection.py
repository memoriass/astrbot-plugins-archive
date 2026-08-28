from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


@dataclass(slots=True, frozen=True)
class CandidateSelection:
    candidate: dict[str, Any]
    confidence: float
    reason: str


def choose_confident_candidate(
    keyword: str,
    candidates: list[dict],
    *,
    threshold: float = 0.88,
    min_margin: float = 0.08,
) -> CandidateSelection | None:
    if not candidates:
        return None

    scored = [
        (score_candidate(keyword, item, index), index, item)
        for index, item in enumerate(candidates)
    ]
    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_index, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < threshold:
        return None
    if len(scored) > 1 and best_score - second_score < min_margin:
        return None
    return CandidateSelection(
        candidate=best,
        confidence=round(best_score, 2),
        reason=_selection_reason(keyword, best, best_index),
    )


def score_candidate(keyword: str, item: dict, index: int) -> float:
    query = _normalize_name(keyword)
    name = _normalize_name(item.get("username") or item.get("uname") or "")
    if not query or not name:
        return 0.0

    if name == query:
        score = 0.97
    elif len(query) >= 2 and query in name:
        score = 0.91
    elif len(name) >= 2 and name in query:
        score = 0.88
    else:
        ratio = SequenceMatcher(None, query, name).ratio()
        if ratio >= 0.86:
            score = 0.86
        elif ratio >= 0.76:
            score = 0.78
        else:
            return 0.0

    score -= min(index * 0.03, 0.12)
    return max(0.0, min(score, 0.99))


def _selection_reason(keyword: str, item: dict, index: int) -> str:
    query = _normalize_name(keyword)
    name = _normalize_name(item.get("username") or item.get("uname") or "")
    if name == query:
        return "UP 名称与关键词完全匹配"
    if query and query in name:
        return "UP 名称包含完整关键词"
    if name and name in query:
        return "关键词包含完整 UP 名称"
    return f"候选相似度最高，排序第 {index + 1}"


def _normalize_name(value: object) -> str:
    text = str(value or "").lower()
    return re.sub(r"[\s\-_./\\|·・,，.。:：;；!！?？'\"“”‘’()（）【】\[\]{}<>《》]+", "", text)
