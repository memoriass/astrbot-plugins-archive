from __future__ import annotations

from typing import Any

from .utils import first_text, normalize_sub_type


def build_readonly_branches(branch_cls, raw: str, params: dict[str, Any], query: str):
    branches = []
    if _wants_account_status(raw):
        branches.append(branch_cls("account_status", "账号状态", "account_status", confidence=0.94, reason="用户询问 Bilibili 登录账号状态"))
    if _wants_live_check(raw):
        branches.append(_live_check_branch(branch_cls, raw))
    if _wants_resolver_status(raw):
        branches.append(branch_cls("diagnose_resolver", "解析诊断", "diagnose_resolver", confidence=0.95, reason="用户询问 UP 解析、别名或召回统计"))
    if _wants_find_subscription(raw):
        branches.append(branch_cls(
            "find_subscription",
            "查找订阅",
            "find_subscription",
            target=query,
            params={"query": query, "sub_type": _list_sub_type(raw, params)},
            confidence=0.92 if query else 0.62,
            reason="用户想在当前会话订阅内查找 UP",
        ))
    return branches


def list_branch(branch_cls, sub_type: str):
    workflow = {
        "live": "list_live_subscriptions",
        "dynamic": "list_dynamic_subscriptions",
    }.get(sub_type, "list_all_subscriptions")
    return branch_cls(
        branch_id=workflow,
        title={"live": "查看直播订阅", "dynamic": "查看动态订阅"}.get(sub_type, "查看全部订阅"),
        workflow=workflow,
        params={"sub_type": sub_type},
        confidence=0.94,
        reason="用户询问当前会话订阅列表",
    )


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


def _live_check_branch(branch_cls, raw: str):
    all_groups = _contains_any(raw, ("全部", "所有", "全群", "全部群"))
    workflow = "check_live_all_groups" if all_groups else "check_live_current_group"
    return branch_cls(
        branch_id=workflow,
        title="检查全部群直播" if all_groups else "检查当前群直播",
        workflow=workflow,
        confidence=0.94 if all_groups else 0.92,
        reason="用户要求手动检查直播状态",
        requires_confirmation=all_groups,
    )


def _wants_account_status(raw: str) -> bool:
    return _contains_any(raw, ("账号", "登录")) and _contains_any(raw, ("状态", "情况", "可用"))


def _wants_resolver_status(raw: str) -> bool:
    return _contains_any(raw, ("解析", "别名", "召回", "命中", "歧义")) and _contains_any(
        raw,
        ("诊断", "统计", "状态", "检查", "情况"),
    )


def _wants_live_check(raw: str) -> bool:
    if "全部检查" in raw or "全部群检查" in raw:
        return True
    return _contains_any(raw, ("直播", "开播")) and _contains_any(
        raw,
        ("检查", "检测", "刷新", "手动"),
    )


def _wants_find_subscription(raw: str) -> bool:
    return _contains_any(raw, ("查找", "搜索", "找一下", "搜一下")) and "订阅" in raw


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)
