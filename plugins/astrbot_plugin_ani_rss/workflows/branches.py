from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .natural_text import (
    clean_anime_query,
    clean_natural_text,
    extract_add_query_and_destination as _extract_add_query_and_destination,
    extract_recommend_query as _extract_recommend_query,
    extract_search_query as _extract_search_query,
    extract_url as _extract_url,
    natural_common_params,
    natural_season_params,
)
from .utils import (
    _first_text,
    _looks_like_mikan_url,
    _looks_like_rss_url,
    _normalize_workflow,
)


@dataclass(frozen=True, slots=True)
class DispatchBranch:
    branch_id: str
    title: str
    workflow: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    requires_confirmation: bool = False


ALLOWED_NEXT_WORKFLOWS = {
    "add_subscription",
    "add_mikan_subscription",
    "recommend_mikan_subscription",
    "search_mikan",
    "list_subscriptions",
    "refresh_subscription",
    "refresh_all",
    "check_status",
    "continue_pending",
}
DISPATCH_CONFIDENCE = 0.80
DISPATCH_MARGIN = 0.07


def build_dispatch_branches(
    text: str,
    params: dict[str, Any] | None = None,
    *,
    require_context: bool = False,
) -> list[DispatchBranch]:
    params = params or {}
    raw = clean_natural_text(_dispatch_text(text, params))
    if not raw:
        return []

    explicit = _explicit_branch(raw, params)
    if explicit:
        return [explicit]
    if require_context and not _has_ani_context(raw, params):
        return []

    common = natural_common_params(raw, params)
    query = _query_from_params_or_text(raw, params)
    branches: list[DispatchBranch] = []

    if _wants_status(raw):
        branches.append(
            _branch(
                "check_status",
                "连接诊断",
                "check_status",
                0.94,
                "用户要求检查 ANI-RSS 连接或插件状态",
            ),
        )

    if _wants_refresh(raw):
        subscription_id = _subscription_id(raw, params)
        if subscription_id:
            branches.append(
                DispatchBranch(
                    branch_id="refresh_subscription",
                    title="刷新单个订阅",
                    workflow="refresh_subscription",
                    target=subscription_id,
                    params={"subscription_id": subscription_id},
                    confidence=0.91,
                    reason="用户要求刷新指定 ANI-RSS 订阅",
                ),
            )
        else:
            branches.append(
                _branch(
                    "refresh_all",
                    "刷新全部订阅",
                    "refresh_all",
                    0.88,
                    "用户要求刷新全部 ANI-RSS 订阅",
                ),
            )

    if _wants_list(raw):
        branches.append(
            DispatchBranch(
                branch_id="list_subscriptions",
                title="查看已启用订阅",
                workflow="list_subscriptions",
                params={**common, "enabled_only": True},
                confidence=0.92,
                reason="用户要求查看正在启用的 ANI-RSS 订阅",
            ),
        )

    if _wants_recommend(raw):
        recommend_query = _extract_recommend_query(raw)
        payload = {**common, **natural_season_params(raw)}
        if recommend_query:
            payload["query"] = recommend_query
        branches.append(
            DispatchBranch(
                branch_id="recommend_mikan_subscription",
                title="推荐 Mikan 番剧",
                workflow="recommend_mikan_subscription",
                target=recommend_query,
                params=payload,
                confidence=0.91,
                reason="用户要求推荐当季或指定条件的番剧候选",
            ),
        )

    if _wants_add(raw):
        rss_url = _extract_url(raw)
        if _looks_like_rss_url(rss_url):
            branches.append(
                DispatchBranch(
                    branch_id="add_rss_subscription",
                    title="RSS 直连添加",
                    workflow="add_subscription",
                    target=rss_url,
                    params={**common, "rss_url": rss_url},
                    confidence=0.96,
                    reason="用户给出了 RSS URL 并表达添加订阅意图",
                    requires_confirmation=True,
                ),
            )
        else:
            title, _destination = _extract_add_query_and_destination(raw)
            title = title or query
            branches.append(
                DispatchBranch(
                    branch_id="add_mikan_subscription",
                    title="Mikan 搜索添加",
                    workflow="add_mikan_subscription",
                    target=title,
                    params={**common, "query": title} if title else common,
                    confidence=0.94 if title else 0.58,
                    reason="用户表达了添加追番订阅意图",
                ),
            )

    if _wants_search(raw):
        mikan_url = _extract_url(raw)
        if _looks_like_mikan_url(mikan_url):
            branches.append(
                DispatchBranch(
                    branch_id="search_mikan_groups",
                    title="查看 Mikan 字幕组",
                    workflow="search_mikan",
                    target=mikan_url,
                    params={"mikan_url": mikan_url},
                    confidence=0.94,
                    reason="用户给出了 Mikan 番剧页并要求查看字幕组",
                ),
            )
        else:
            search_query = _extract_search_query(raw) or query
            branches.append(
                DispatchBranch(
                    branch_id="search_mikan",
                    title="搜索 Mikan",
                    workflow="search_mikan",
                    target=search_query,
                    params={"query": search_query} if search_query else {},
                    confidence=0.89 if search_query else 0.55,
                    reason="用户表达了搜索番剧或字幕组意图",
                ),
            )

    return sorted(
        [branch for branch in branches if branch],
        key=lambda item: item.confidence,
        reverse=True,
    )


def is_ani_dispatch_candidate(text: str) -> bool:
    return bool(build_dispatch_branches(text, require_context=True))


def select_dispatch_branch(
    branches: list[DispatchBranch],
    params: dict[str, Any] | None = None,
) -> DispatchBranch | None:
    params = params or {}
    selected_id = _first_text(params, "branch_id", "selected_branch", "branch")
    if selected_id:
        return _match_selected_branch(branches, selected_id)
    if not branches:
        return None

    top = branches[0]
    runner_up = branches[1] if len(branches) > 1 else None
    if top.confidence < DISPATCH_CONFIDENCE:
        return None
    if runner_up and top.confidence - runner_up.confidence < DISPATCH_MARGIN:
        return None
    return top


def format_dispatch_options(branches: list[DispatchBranch]) -> str:
    if not branches:
        return (
            "没有识别到明确的 ANI-RSS 操作。请说明要搜索番剧、推荐新番、"
            "添加订阅、查看订阅列表、刷新订阅还是检查状态。"
        )
    lines = ["需要补充要执行的 ANI-RSS 操作："]
    for branch in branches[:3]:
        target = f"：{branch.target}" if branch.target else ""
        confirm = "，需选择/确认" if branch.requires_confirmation else ""
        lines.append(f"- {branch.title}{target}{confirm}")
    return "\n".join(lines)


def _explicit_branch(raw: str, params: dict[str, Any]) -> DispatchBranch | None:
    workflow = _normalize_workflow(
        _first_text(params, "next_workflow", "workflow", "intent", "action"),
    )
    if workflow in {"", "ai_dispatch"} or workflow not in ALLOWED_NEXT_WORKFLOWS:
        return None
    target, payload = _params_for_workflow(workflow, raw, params)
    return DispatchBranch(
        branch_id=workflow,
        title=f"进入 {workflow}",
        workflow=workflow,
        target=target,
        params=payload,
        confidence=0.98,
        reason="AI 工具显式给出了受支持的 workflow",
        requires_confirmation=workflow == "add_subscription",
    )


def _params_for_workflow(
    workflow: str,
    raw: str,
    params: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    payload = natural_common_params(raw, params)
    if workflow == "add_subscription":
        rss_url = _first_text(payload, "rss_url", "url", "target") or _extract_url(raw)
        if rss_url:
            payload["rss_url"] = rss_url
        return rss_url, payload
    if workflow in {"add_mikan_subscription", "search_mikan"}:
        target = _query_from_params_or_text(raw, payload)
        if target:
            payload.setdefault("query", target)
        return target, payload
    if workflow == "recommend_mikan_subscription":
        target = _query_from_params_or_text(raw, payload)
        payload.update(natural_season_params(raw))
        if target:
            payload.setdefault("query", target)
        return target, payload
    if workflow == "list_subscriptions":
        payload["enabled_only"] = True
        return "", payload
    if workflow == "refresh_subscription":
        target = _subscription_id(raw, payload)
        if target:
            payload.setdefault("subscription_id", target)
        return target, payload
    if workflow == "continue_pending":
        return _first_text(payload, "task_id", "id", "target"), payload
    return "", payload


def _branch(
    branch_id: str,
    title: str,
    workflow: str,
    confidence: float,
    reason: str,
) -> DispatchBranch:
    return DispatchBranch(
        branch_id=branch_id,
        title=title,
        workflow=workflow,
        confidence=confidence,
        reason=reason,
    )


def _dispatch_text(text: str, params: dict[str, Any]) -> str:
    return _first_text(
        {"target": text, **params},
        "text",
        "message",
        "prompt",
        "query",
        "title",
        "name",
        "target",
        "_raw",
        "value",
    )


def _query_from_params_or_text(raw: str, params: dict[str, Any]) -> str:
    query = _first_text(params, "query", "title", "name", "keyword", "target", "text")
    if query and query != raw:
        return clean_anime_query(query)
    if _wants_search(raw):
        return _extract_search_query(raw)
    if _wants_recommend(raw):
        return _extract_recommend_query(raw)
    title, _destination = _extract_add_query_and_destination(raw)
    return title or clean_anime_query(raw)


def _subscription_id(text: str, params: dict[str, Any]) -> str:
    value = _first_text(params, "subscription_id", "id")
    if value:
        return value
    match = re.search(r"(?:id|ID|订阅)\s*[:：#]?\s*([A-Za-z0-9_-]{6,})", text)
    return match.group(1) if match else ""


def _has_ani_context(raw: str, params: dict[str, Any]) -> bool:
    if _first_text(
        params,
        "workflow",
        "next_workflow",
        "intent",
        "action",
        "query",
        "title",
        "rss_url",
        "mikan_url",
        "url",
    ):
        return True
    if _extract_url(raw):
        return True
    if _contains_any(raw, _DIRECT_CONTEXT_TOKENS):
        return True
    if _contains_any(raw, _ANIME_CONTEXT_TOKENS) and _contains_any(raw, _OPERATION_TOKENS):
        return True
    if _wants_add(raw) and bool(_extract_add_query_and_destination(raw)[0]):
        return True
    return False


def _wants_status(raw: str) -> bool:
    return bool(
        re.search(r"(?:检查|测试|诊断).{0,30}(?:ani-rss|anirss|连接|状态|插件)", raw, re.IGNORECASE),
    )


def _wants_refresh(raw: str) -> bool:
    return bool(
        re.search(r"(?:刷新|更新).{0,40}(?:ani-rss|anirss|全部订阅|所有订阅|订阅)", raw, re.IGNORECASE),
    )


def _wants_list(raw: str) -> bool:
    return bool(
        re.search(
            r"(?:查看|列出|看看|显示|预览).{0,40}"
            r"(?:ani-rss|anirss|订阅列表|订阅|追番|已启用|运行|正在订阅)",
            raw,
            re.IGNORECASE,
        ),
    )


def _wants_recommend(raw: str) -> bool:
    if _wants_add(raw) or _wants_search(raw):
        return False
    return bool(
        re.search(
            r"(?:列出|推荐|看看|看下|来点|有什么|有没有).{0,50}(?:当季|本季|当前季度|新番|番剧|动画|追番|推荐)",
            raw,
            re.IGNORECASE,
        ),
    )


def _wants_add(raw: str) -> bool:
    if re.search(r"(?:不要|不用|先不|无需|别)\s*(?:添加|下载|订阅|追番|加入)", raw):
        return False
    if re.search(r"(?:查看|列出|显示|搜索|查找|查一下|找一下|搜一下|刷新|更新)", raw):
        return False
    return bool(
        re.search(
            r"(?:添加|下载|订阅|追番|加入).{1,80}(?:ani|ani-rss|anirss|nas|rss|订阅|番剧|动画|字幕组)?",
            raw,
            re.IGNORECASE,
        ),
    )


def _wants_search(raw: str) -> bool:
    return bool(
        re.search(
            r"(?:搜索|查找|查一下|找一下|搜一下).{0,80}(?:mikan|蜜柑|字幕组|番剧|动画|rss|有没有字幕组)",
            raw,
            re.IGNORECASE,
        )
        or re.search(r"有没有.{0,40}字幕组", raw),
    )


def _match_selected_branch(
    branches: list[DispatchBranch],
    selected_id: str,
) -> DispatchBranch | None:
    key = str(selected_id or "").strip().lower()
    for branch in branches:
        if key in {branch.branch_id.lower(), branch.workflow.lower(), branch.title.lower()}:
            return branch
    return None


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(token.lower() in lower for token in tokens)


_DIRECT_CONTEXT_TOKENS = (
    "ani-rss",
    "anirss",
    "ani rss",
    "mikan",
    "蜜柑",
    "rss",
    "字幕组",
)

_ANIME_CONTEXT_TOKENS = (
    "番剧",
    "动画",
    "新番",
    "追番",
)

_OPERATION_TOKENS = (
    "添加",
    "下载",
    "订阅",
    "加入",
    "搜索",
    "查找",
    "推荐",
    "列出",
    "查看",
    "刷新",
    "更新",
)
