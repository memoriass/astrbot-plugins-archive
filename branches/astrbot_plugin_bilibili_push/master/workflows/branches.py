from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .utils import first_text, normalize_sub_type, normalize_workflow


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
    "search_up",
    "add_subscription",
    "remove_subscription",
    "list_subscriptions",
    "list_all_subscriptions",
    "list_live_subscriptions",
    "list_dynamic_subscriptions",
    "find_subscription",
    "account_status",
    "diagnose_health",
    "diagnose_resolver",
    "check_live_current_group",
    "check_live_all_groups",
    "check_status",
    "continue_pending",
}
DISPATCH_CONFIDENCE = 0.82
DISPATCH_MARGIN = 0.08


def build_dispatch_branches(
    text: str,
    params: dict[str, Any] | None = None,
    *,
    require_context: bool = False,
) -> list[DispatchBranch]:
    params = params or {}
    raw = str(text or "").strip()
    explicit = _explicit_branch(raw, params)
    if explicit:
        return [explicit]
    if require_context and not _has_bili_context(raw, params):
        return []

    query = _query_from_params_or_text(raw, params)
    sub_type = _subscription_type(raw, params)
    branches: list[DispatchBranch] = []

    from .branch_readonly import build_readonly_branches, list_branch

    branches.extend(build_readonly_branches(DispatchBranch, raw, params, query))
    if _wants_list(raw):
        list_sub_type = _list_sub_type(raw, params)
        branches.append(list_branch(DispatchBranch, list_sub_type))
    if _wants_remove(raw):
        branches.append(_remove_branch(query, sub_type))
    if _wants_add(raw, params):
        branches.append(_add_branch(query, sub_type))
    if _wants_search(raw, params):
        branches.append(_search_branch(query))

    return sorted(
        [branch for branch in branches if branch],
        key=lambda item: item.confidence,
        reverse=True,
    )


def is_bili_dispatch_candidate(text: str) -> bool:
    return bool(build_dispatch_branches(text, require_context=True))


def select_dispatch_branch(
    branches: list[DispatchBranch],
    params: dict[str, Any],
) -> DispatchBranch | None:
    selected_id = first_text(params, "branch_id", "selected_branch", "branch")
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


def _match_selected_branch(
    branches: list[DispatchBranch],
    selected_id: str,
) -> DispatchBranch | None:
    selected = str(selected_id or "").strip()
    if not selected:
        return None
    normalized = normalize_workflow(selected)
    lowered = selected.lower()
    for branch in branches:
        candidates = {
            branch.branch_id,
            branch.workflow,
            normalize_workflow(branch.workflow),
            branch.title,
        }
        if selected in candidates or normalized in candidates:
            return branch
        if lowered in {str(item).lower() for item in candidates}:
            return branch
    return None


def format_dispatch_options(branches: list[DispatchBranch]) -> str:
    if not branches:
        return "没有识别到明确的 Bilibili 操作，请说明要搜索、订阅、删除还是查看状态。"
    lines = ["识别到多个可能的 Bilibili 操作，请补充要执行哪一个："]
    for branch in branches[:5]:
        target = f" | target={branch.target}" if branch.target else ""
        confirm = " | 需要确认" if branch.requires_confirmation else ""
        lines.append(
            f"- {branch.branch_id}: {branch.title}{target}{confirm} | 置信度 {branch.confidence:.0%}"
        )
    return "\n".join(lines)


def _explicit_branch(raw: str, params: dict[str, Any]) -> DispatchBranch | None:
    workflow = normalize_workflow(
        first_text(params, "next_workflow", "workflow", "intent", "action")
    )
    if workflow in {"", "ai_dispatch"} or workflow not in ALLOWED_NEXT_WORKFLOWS:
        return None
    query = _query_from_params_or_text(raw, params)
    sub_type = _subscription_type(raw, params)
    return DispatchBranch(
        branch_id=workflow,
        title=f"进入 {workflow}",
        workflow=workflow,
        target=query,
        params=_params_for_workflow(workflow, query, sub_type, params),
        confidence=0.98,
        reason="AI 工具显式给出了受支持的后续 workflow",
        requires_confirmation=workflow in {
            "add_subscription",
            "remove_subscription",
            "check_live_all_groups",
        },
    )


def _branch(
    branch_id: str,
    title: str,
    workflow: str,
    confidence: float,
    reason: str,
) -> DispatchBranch:
    return DispatchBranch(branch_id, title, workflow, confidence=confidence, reason=reason)


def _add_branch(query: str, sub_type: str) -> DispatchBranch:
    confidence = 0.94 if query else 0.58
    label = {"live": "添加直播订阅", "both": "添加动态和直播订阅"}.get(sub_type, "添加动态订阅")
    return DispatchBranch(
        branch_id=f"add_{sub_type}",
        title=label,
        workflow="add_subscription",
        target=query,
        params={"query": query, "sub_type": sub_type},
        confidence=confidence,
        reason="用户表达了添加订阅意图",
        requires_confirmation=True,
    )


def _remove_branch(query: str, sub_type: str) -> DispatchBranch:
    confidence = 0.94 if query else 0.58
    return DispatchBranch(
        branch_id=f"remove_{sub_type}",
        title="删除订阅",
        workflow="remove_subscription",
        target=query,
        params={"uid": query, "sub_type": sub_type},
        confidence=confidence,
        reason="用户表达了删除或取消订阅意图",
        requires_confirmation=True,
    )


def _search_branch(query: str) -> DispatchBranch:
    return DispatchBranch(
        branch_id="search_up",
        title="搜索 UP 主",
        workflow="search_up",
        target=query,
        params={"query": query},
        confidence=0.88 if query else 0.55,
        reason="用户表达了搜索或查找 UP 主意图",
    )


def _params_for_workflow(
    workflow: str,
    query: str,
    sub_type: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if workflow == "add_subscription":
        return {"query": query, "sub_type": sub_type}
    if workflow == "remove_subscription":
        return {"uid": query, "sub_type": sub_type}
    if workflow == "search_up":
        return {"query": query}
    if workflow == "find_subscription":
        return {"query": query, "sub_type": sub_type}
    if workflow == "list_live_subscriptions":
        return {"sub_type": "live"}
    if workflow == "list_dynamic_subscriptions":
        return {"sub_type": "dynamic"}
    if workflow == "list_all_subscriptions":
        return {"sub_type": "both"}
    if workflow == "continue_pending":
        return dict(params)
    return {}


def _query_from_params_or_text(raw: str, params: dict[str, Any]) -> str:
    query = first_text(params, "uid", "query", "keyword", "target", "name", "text")
    if query and query != raw:
        return query
    return extract_up_keyword(raw)


def _subscription_type(raw: str, params: dict[str, Any]) -> str:
    explicit = first_text(params, "sub_type", "type")
    if explicit:
        return normalize_sub_type(explicit)
    has_dynamic = "动态" in raw
    has_live = "直播" in raw
    if has_dynamic and has_live:
        return "both"
    if has_live:
        return "live"
    return "dynamic"


def _list_sub_type(raw: str, params: dict[str, Any]) -> str:
    explicit = first_text(params, "sub_type", "type")
    if explicit:
        return normalize_sub_type(explicit)
    has_dynamic = "动态" in raw
    has_live = "直播" in raw
    if has_dynamic and has_live:
        return "both"
    if has_live:
        return "live"
    if has_dynamic:
        return "dynamic"
    return "both"


def extract_up_keyword(text: str) -> str:
    value = _strip_wake_prefix(str(text or "").strip())
    phrase_keyword = _keyword_from_subscription_phrase(value)
    if phrase_keyword:
        return phrase_keyword
    value = re.sub(r"https?://\S+", " ", value)
    for token in _NOISE_TOKENS:
        value = re.sub(re.escape(token), " ", value, flags=re.IGNORECASE)
    value = re.sub(r"[,，.。!！?？、;；:：()\[\]{}<>《》【】\"'“”‘’]+", " ", value)
    parts = [part for part in re.split(r"\s+", value) if part]
    if not parts:
        return str(text or "").strip()
    return _best_keyword_part(parts)


def _strip_wake_prefix(text: str) -> str:
    return re.sub(r"^[A-Za-z0-9_\-]{1,24}\s+", "", text, count=1).strip()


def _keyword_from_subscription_phrase(text: str) -> str:
    for pattern in _SUBSCRIPTION_KEYWORD_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group("keyword").strip()
    return ""


def _best_keyword_part(parts: list[str]) -> str:
    for part in reversed(parts):
        if re.search(r"[A-Za-z0-9_\-\u4e00-\u9fff]", part):
            return part
    return parts[-1]


def _has_bili_context(raw: str, params: dict[str, Any]) -> bool:
    if first_text(params, "workflow", "next_workflow", "intent", "query", "keyword", "uid"):
        return True
    if _contains_any(raw, _BILI_TOKENS):
        return True
    if "全部检查" in raw or "全部群检查" in raw:
        return True
    if (
        _contains_any(raw, ("账号", "别名", "解析", "命中", "歧义", "召回"))
        and _contains_any(raw, ("检查", "诊断", "统计", "状态", "情况", "健康"))
        and _contains_any(raw, ("订阅", "直播", "动态", "推送", "UP", "up", *_BILI_TOKENS))
    ):
        return True
    if _has_subscription_context(raw):
        return True
    return _contains_any(raw, ("订阅", "直播", "动态", "推送", "提醒")) and _contains_any(
        raw,
        (
            "添加",
            "新增",
            "创建",
            "开启",
            "打开",
            "开通",
            "设置",
            "删除",
            "取消",
            "移除",
            "退订",
            "查看",
            "列表",
            "检查",
            "检测",
            "查找",
            "搜索",
        ),
    )


def _has_subscription_context(raw: str) -> bool:
    return _contains_any(
        raw,
        ("订阅", "关注", "添加", "新增", "创建", "开", "开启", "打开", "开通", "设置"),
    ) and _contains_any(
        raw,
        ("直播", "动态", "推送", "提醒", "通知", "UP", "up"),
    )


def _wants_list(raw: str) -> bool:
    return _contains_any(raw, ("列表", "有哪些", "查看", "当前")) and _contains_any(
        raw,
        ("订阅", "UP", "up"),
    )


def _wants_add(raw: str, params: dict[str, Any]) -> bool:
    if normalize_workflow(first_text(params, "intent", "action")) == "add_subscription":
        return True
    has_add_verb = _contains_any(
        raw,
        ("添加", "新增", "创建", "关注", "开", "开启", "打开", "开通", "设置"),
    )
    if not has_add_verb:
        if "订阅" not in raw:
            return False
        if _contains_any(raw, ("列表", "有哪些", "查看", "删除", "取消", "移除", "退订")):
            return False
    return _contains_any(
        raw,
        ("订阅", "添加", "新增", "创建", "关注", "开", "开启", "打开", "开通", "设置"),
    ) and _contains_any(
        raw,
        ("动态", "直播", "UP", "up", "b站", "B站", "bilibili", "提醒", "通知"),
    )


def _wants_remove(raw: str) -> bool:
    return _contains_any(raw, ("删除", "取消", "移除", "退订")) and _contains_any(
        raw,
        ("订阅", "直播", "动态", "推送", "提醒", "UP", "up"),
    )


def _wants_search(raw: str, params: dict[str, Any]) -> bool:
    if normalize_workflow(first_text(params, "intent", "action")) == "search_up":
        return True
    return _contains_any(raw, ("搜索", "查找", "找一下", "搜一下"))


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


_BILI_TOKENS = (
    "bilibili",
    "Bilibili",
    "bili",
    "B站",
    "b站",
    "UP主",
    "up主",
    "UP",
)


_SUBSCRIPTION_KEYWORD_PATTERNS = (
    r"(?:订阅|关注|添加|新增|创建)\s*(?:B站|b站|bilibili)?\s*(?:直播|动态)?\s*"
    r"(?P<keyword>[A-Za-z0-9][A-Za-z0-9_.\-]{1,80})"
    r"(?=\s*的?\s*(?:B站|b站|bilibili)?\s*(?:直播|动态|推送|提醒|通知|$))",
    r"(?:搜索|查找|找一下|搜一下)\s*(?P<keyword>[A-Za-z0-9][A-Za-z0-9_.\-]{1,80})",
)


_NOISE_TOKENS = (
    "添加",
    "新增",
    "创建",
    "开",
    "开启",
    "打开",
    "开通",
    "设置",
    "删除",
    "取消",
    "移除",
    "退订",
    "订阅",
    "关注",
    "搜索",
    "查找",
    "找一下",
    "搜一下",
    "帮我",
    "给我",
    "请",
    "一下",
    "一个",
    "bilibili",
    "Bilibili",
    "bili",
    "B站",
    "b站",
    "UP主",
    "up主",
    "UP",
    "up",
    "动态",
    "直播",
    "推送",
    "提醒",
    "通知",
)
