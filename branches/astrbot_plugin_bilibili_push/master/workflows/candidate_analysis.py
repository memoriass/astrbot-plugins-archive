from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger

from .runtime import event_origin
from .selection import CandidateSelection, score_candidate


@dataclass(frozen=True, slots=True)
class CandidateAnalysisConfig:
    enabled: bool
    min_confidence: float
    timeout_sec: float


async def analyze_search_candidates(
    plugin: Any,
    event,
    keyword: str,
    candidates: list[dict],
    *,
    sub_type: str = "dynamic",
    intent: str = "add_subscription",
) -> CandidateSelection | None:
    cfg = _analysis_config(plugin)
    if not cfg.enabled or not candidates:
        return None

    provider = _get_provider(plugin, event)
    if provider is None:
        return None

    prompt = _build_prompt(keyword, candidates, sub_type=sub_type, intent=intent)
    try:
        response = await asyncio.wait_for(
            provider.text_chat(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                session_id=event_origin(event),
            ),
            timeout=cfg.timeout_sec,
        )
    except Exception as exc:
        logger.debug(f"Bilibili candidate analysis fallback: {exc}")
        return None

    payload = _parse_json(_response_text(response))
    if not payload:
        return None

    confidence = _safe_confidence(payload.get("confidence"))
    if confidence < cfg.min_confidence:
        return None

    selected = _candidate_from_payload(payload, candidates)
    if selected is None:
        return None
    reason = str(payload.get("reason") or "AI 候选分析").strip()
    return CandidateSelection(
        candidate=selected,
        confidence=round(confidence, 2),
        reason=f"AI 候选分析：{reason}",
    )


def _analysis_config(plugin: Any) -> CandidateAnalysisConfig:
    return CandidateAnalysisConfig(
        enabled=bool(getattr(plugin, "enable_ai_candidate_analysis", True)),
        min_confidence=float(getattr(plugin, "ai_candidate_analysis_confidence", 0.86)),
        timeout_sec=float(getattr(plugin, "ai_candidate_analysis_timeout_sec", 8.0)),
    )


def _get_provider(plugin: Any, event) -> Any:
    context = getattr(plugin, "context", None)
    getter = getattr(context, "get_using_provider", None)
    if not callable(getter):
        return None
    try:
        return getter(umo=event_origin(event))
    except Exception as exc:
        logger.debug(f"Bilibili candidate analysis provider unavailable: {exc}")
        return None


def _build_prompt(
    keyword: str,
    candidates: list[dict],
    *,
    sub_type: str,
    intent: str,
) -> str:
    return json.dumps(
        {
            "keyword": str(keyword or ""),
            "intent": intent,
            "sub_type": sub_type,
            "candidates": [
                _candidate_hint(keyword, item, index)
                for index, item in enumerate(candidates[:8])
            ],
            "output_schema": {
                "selected_index": "1-based index, or 0 when unclear",
                "selected_uid": "uid from candidates, or empty when unclear",
                "confidence": "0.0-1.0",
                "reason": "short Chinese reason",
            },
        },
        ensure_ascii=False,
        default=str,
    )


def _candidate_hint(keyword: str, item: dict, index: int) -> dict[str, Any]:
    return {
        "index": index + 1,
        "uid": str(item.get("uid") or item.get("mid") or ""),
        "username": str(item.get("username") or item.get("uname") or ""),
        "sub_type": str(item.get("sub_type") or ""),
        "tags": item.get("tags") or [],
        "follower": item.get("follower") if item.get("follower") is not None else item.get("fans"),
        "search_rank": index + 1,
        "name_score": round(score_candidate(keyword, item, index), 3),
    }


def _response_text(response: Any) -> str:
    text = getattr(response, "completion_text", "")
    if text:
        return str(text)
    result_chain = getattr(response, "result_chain", None)
    chain = getattr(result_chain, "chain", None)
    if not chain:
        return ""
    return "\n".join(str(getattr(item, "text", item)) for item in chain)


def _parse_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        raw = match.group(0)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _candidate_from_payload(
    payload: dict[str, Any],
    candidates: list[dict],
) -> dict | None:
    uid = str(payload.get("selected_uid") or payload.get("uid") or "").strip()
    if uid:
        for candidate in candidates:
            if str(candidate.get("uid") or candidate.get("mid") or "") == uid:
                return candidate

    try:
        index = int(payload.get("selected_index") or payload.get("index") or 0)
    except (TypeError, ValueError):
        return None
    if index <= 0 or index > len(candidates):
        return None
    return candidates[index - 1]


def _safe_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(confidence, 1.0))


_SYSTEM_PROMPT = """你是 Bilibili workflow 的候选分析器。
只输出一个 JSON 对象，不要输出 Markdown，不要解释。

任务：
1. 根据 intent、用户关键词、候选名称、候选类型、搜索排序、粉丝数和 name_score 判断是否有足够明确的目标 UP。
2. 你只代理判断下一步分支：高置信时选择一个候选进入后续确认或高亮；不清晰时 selected_index=0、selected_uid=""。
3. 不能写库，不能确认订阅，不能选择候选列表之外的 UID。

判断原则：
- 名称强相关是第一要素；粉丝数差距可以作为辅助证据，不能单独决定。
- 如果候选名称接近、搜索排序靠前、粉丝数显著高于其他同名/近似候选，可以提高置信度。
- 如果关键词是别名、简称、繁简差异或网络代称，可以结合搜索排序和粉丝量做合理判断。
- intent=remove_subscription 时，候选来自当前会话已有订阅；只判断用户想删除哪一个订阅，高置信也只能进入删除确认卡。
- intent=search_up 时，只判断哪个搜索结果最可能，不要把搜索意图改成订阅意图。
- 如果多个候选都可能正确，或只是粉丝高但名称不匹配，应返回低置信。
- 高置信建议 confidence >= 0.86；不确定时 confidence < 0.86。
"""
