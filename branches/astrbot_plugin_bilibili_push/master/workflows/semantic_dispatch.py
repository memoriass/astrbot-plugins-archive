from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger

from .branches import ALLOWED_NEXT_WORKFLOWS, DispatchBranch
from .entity_resolver import resolve_up_candidates
from .runtime import event_origin
from .utils import first_text, normalize_sub_type, normalize_workflow


_PUBLIC_SEMANTIC_WORKFLOWS = ALLOWED_NEXT_WORKFLOWS - {
    "diagnose_health",
    "check_status",
}


@dataclass(frozen=True, slots=True)
class SemanticDispatchConfig:
    enabled: bool
    min_confidence: float
    timeout_sec: float


async def analyze_semantic_dispatch(
    plugin: Any,
    event,
    text: str,
    params: dict[str, Any],
    *,
    branches: list[DispatchBranch] | None = None,
) -> DispatchBranch | None:
    cfg = _semantic_config(plugin)
    if not cfg.enabled:
        return None
    if _has_explicit_workflow(params):
        return None

    provider = _get_provider(plugin, event)
    if provider is None:
        return None

    branches = branches or []
    prompt = _build_prompt(
        text,
        params,
        branches=branches,
        recall_candidates=_semantic_recall(plugin, event, text, params, branches),
    )
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
        logger.debug(f"Bilibili semantic dispatch fallback: {exc}")
        return None

    payload = _parse_json(_response_text(response))
    if not payload:
        return None
    branch = _branch_from_payload(payload, branches)
    if branch is None or branch.confidence < cfg.min_confidence:
        return None
    return branch


def _semantic_config(plugin: Any) -> SemanticDispatchConfig:
    return SemanticDispatchConfig(
        enabled=bool(getattr(plugin, "enable_ai_semantic_dispatch", True)),
        min_confidence=float(getattr(plugin, "ai_semantic_dispatch_confidence", 0.82)),
        timeout_sec=float(getattr(plugin, "ai_semantic_dispatch_timeout_sec", 8.0)),
    )


def _has_explicit_workflow(params: dict[str, Any]) -> bool:
    return bool(first_text(params, "workflow", "next_workflow", "intent", "action"))


def _get_provider(plugin: Any, event) -> Any:
    context = getattr(plugin, "context", None)
    getter = getattr(context, "get_using_provider", None)
    if not callable(getter):
        return None
    try:
        return getter(umo=event_origin(event))
    except Exception as exc:
        logger.debug(f"Bilibili semantic dispatch provider unavailable: {exc}")
        return None


def _build_prompt(
    text: str,
    params: dict[str, Any],
    *,
    branches: list[DispatchBranch],
    recall_candidates: list[dict[str, Any]],
) -> str:
    return json.dumps(
        {
            "user_text": str(text or ""),
            "params": params or {},
            "allowed_workflows": sorted(_PUBLIC_SEMANTIC_WORKFLOWS),
            "fallback_branches": [_branch_hint(branch) for branch in branches[:5]],
            "semantic_recall": recall_candidates,
            "output_schema": {
                "workflow": "one value from allowed_workflows, or none",
                "query": "UP name, nickname, UID, or empty string",
                "sub_type": "dynamic | live | both",
                "confidence": "0.0-1.0",
                "reason": "short Chinese reason",
            },
        },
        ensure_ascii=False,
        default=str,
    )


def _branch_hint(branch: DispatchBranch) -> dict[str, Any]:
    return {
        "branch_id": branch.branch_id,
        "title": branch.title,
        "workflow": branch.workflow,
        "target": branch.target,
        "params": dict(branch.params),
        "confidence": branch.confidence,
        "reason": branch.reason,
        "requires_confirmation": branch.requires_confirmation,
    }


def _semantic_recall(
    plugin: Any,
    event,
    text: str,
    params: dict[str, Any],
    branches: list[DispatchBranch],
) -> list[dict[str, Any]]:
    target_id = event_origin(event)
    queries = _recall_queries(text, params, branches)
    recalled: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for query in queries:
        try:
            candidates = resolve_up_candidates(plugin, target_id, query)
        except Exception as exc:
            logger.debug(f"Bilibili semantic recall fallback: {exc}")
            continue
        for candidate in candidates[:5]:
            key = (candidate.uid, candidate.source)
            if key in seen:
                continue
            seen.add(key)
            recalled.append(
                {
                    "query": query,
                    "uid": candidate.uid,
                    "username": candidate.username,
                    "confidence": candidate.confidence,
                    "source": candidate.source,
                    "reason": candidate.reason,
                }
            )
            if len(recalled) >= 8:
                return recalled
    return recalled


def _recall_queries(
    text: str,
    params: dict[str, Any],
    branches: list[DispatchBranch],
) -> list[str]:
    values = [
        first_text(params, "uid", "query", "keyword", "target", "name"),
        *[branch.target for branch in branches],
        *[
            first_text(branch.params, "uid", "query", "keyword", "target", "name")
            for branch in branches
        ],
    ]
    if not values:
        values.append(text)
    result = []
    seen = set()
    for value in values:
        query = str(value or "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        result.append(query)
    return result[:5]


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


def _branch_from_payload(
    payload: dict[str, Any],
    branches: list[DispatchBranch],
) -> DispatchBranch | None:
    workflow = normalize_workflow(str(payload.get("workflow") or ""))
    if workflow in {"", "none", "ai_dispatch"}:
        return None
    if workflow not in _PUBLIC_SEMANTIC_WORKFLOWS:
        return None

    fallback = _fallback_branch(workflow, branches)
    query = str(
        payload.get("query")
        or payload.get("target")
        or (fallback.target if fallback else "")
        or ""
    ).strip()
    default_type = "both" if workflow == "list_subscriptions" else "dynamic"
    sub_type = normalize_sub_type(
        str(
            payload.get("sub_type")
            or (fallback.params.get("sub_type") if fallback else "")
            or default_type
        )
    )
    confidence = _safe_confidence(payload.get("confidence"))
    reason = str(payload.get("reason") or "LLM 语义分流").strip()
    return DispatchBranch(
        branch_id=f"semantic_{workflow}",
        title=f"AI 语义分流: {workflow}",
        workflow=workflow,
        target=query,
        params=_params_for_workflow(workflow, query, sub_type),
        confidence=confidence,
        reason=reason,
        requires_confirmation=workflow in {"add_subscription", "remove_subscription"},
    )


def _params_for_workflow(workflow: str, query: str, sub_type: str) -> dict[str, Any]:
    if workflow == "add_subscription":
        return {"query": query, "sub_type": sub_type}
    if workflow == "remove_subscription":
        return {"uid": query, "sub_type": sub_type}
    if workflow == "list_subscriptions":
        return {"sub_type": sub_type}
    if workflow == "search_up":
        return {"query": query}
    if workflow == "continue_pending":
        return {"action": query}
    return {}


def _fallback_branch(
    workflow: str,
    branches: list[DispatchBranch],
) -> DispatchBranch | None:
    matches = [branch for branch in branches if branch.workflow == workflow]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item.confidence, reverse=True)[0]


def _safe_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(confidence, 1.0))


_SYSTEM_PROMPT = """你是 Bilibili 订阅插件的前置语义分流器。
只输出一个 JSON 对象，不要输出 Markdown，不要解释。

任务：
1. 判断用户是否要操作 Bilibili/UP 主/直播/动态/订阅/推送/账号。
2. 综合 fallback_branches 和 semantic_recall，在允许的 workflow 中选择一个。
3. 抽取 UP 名称、简称、网络代称或 UID 到 query；如果 semantic_recall 给出可信候选，可沿用用户称呼或该候选 UID，但不要编造 UID。
4. 判断订阅类型：直播 live，动态 dynamic，同时需要两者 both。
5. 只有用户意图清晰时 confidence >= 0.82；不清晰时 workflow 为 none 或 confidence 低于 0.82。

边界：
- 不要编造 UID。
- semantic_recall 是当前订阅、标签和历史别名召回，属于证据；如果候选分歧明显，不要强行选择。
- fallback_branches 是确定性规则分流结果；你可以修正它，但必须保持在 allowed_workflows 内。
- 你只做分流和 query/sub_type 归一，不写库，不跳过后续用户确认。
- “订阅直播 noworld”“订阅 noworld 的直播”“给 noworld 开直播提醒”都应是 add_subscription，query=noworld，sub_type=live。
- “订阅动态 noworld”“关注 noworld 动态”是 add_subscription，sub_type=dynamic。
- “删除/取消/退订 noworld 直播订阅”是 remove_subscription，sub_type=live。
- “查看订阅/有哪些订阅”是 list_subscriptions。
- “账号状态/登录状态”是 account_status。
- “插件状态/检查状态/健康诊断”不是面向聊天侧的自然语言入口，应返回 workflow=none；内部显式 workflow 另行处理。
"""
