from __future__ import annotations

import re

from .models import WorkflowRequest


def workflow_from_natural_language(text: str) -> WorkflowRequest | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if re.search(r"(?:账号|登录).{0,12}(?:状态|情况)", raw):
        return WorkflowRequest("account_status", source="natural")
    if re.search(r"(?:诊断|检查|测试).{0,12}(?:状态|连接|插件|b站|B站)", raw):
        return WorkflowRequest("check_status", source="natural")
    if re.search(r"(?:列表|有哪些|查看).{0,12}(?:订阅|UP)", raw):
        return WorkflowRequest("list_subscriptions", source="natural")
    if re.search(r"(?:搜索|查找|找一下|搜一下)", raw):
        return WorkflowRequest("search_up", target=raw, params={"query": raw}, source="natural")
    if re.search(r"(?:订阅|添加).{0,40}(?:动态|直播|UP|up)", raw):
        sub_type = "live" if "直播" in raw else "dynamic"
        return WorkflowRequest(
            "add_subscription",
            target=raw,
            params={"query": raw, "sub_type": sub_type},
            source="natural",
        )
    return None
