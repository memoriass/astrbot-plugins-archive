from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowRequest:
    workflow: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "tool"


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    workflow: str
    title: str
    purpose: str
    user_visible: bool = True


COMPILED_WORKFLOWS: dict[str, CompiledWorkflow] = {
    "search_up": CompiledWorkflow(
        "search_up",
        "搜索 UP 主",
        "按关键词搜索 UP 主，返回候选和 pending task。",
    ),
    "add_subscription": CompiledWorkflow(
        "add_subscription",
        "添加订阅",
        "按明确 UID 添加动态或直播订阅；按关键词时先搜索并要求确认。",
    ),
    "remove_subscription": CompiledWorkflow(
        "remove_subscription",
        "删除订阅",
        "删除当前会话的动态或直播订阅。",
    ),
    "list_subscriptions": CompiledWorkflow(
        "list_subscriptions",
        "订阅列表",
        "列出当前会话订阅。",
    ),
    "account_status": CompiledWorkflow(
        "account_status",
        "账号状态",
        "查看 Bilibili 登录账号池状态。",
    ),
    "check_status": CompiledWorkflow(
        "check_status",
        "诊断状态",
        "检查插件关键依赖和账号池状态。",
    ),
    "continue_pending": CompiledWorkflow(
        "continue_pending",
        "继续任务",
        "继续搜索候选选择或确认添加。",
    ),
}


WORKFLOW_ALIASES = {
    "search": "search_up",
    "search_user": "search_up",
    "search_up": "search_up",
    "搜索": "search_up",
    "查找": "search_up",
    "add": "add_subscription",
    "subscribe": "add_subscription",
    "add_subscription": "add_subscription",
    "订阅": "add_subscription",
    "添加": "add_subscription",
    "remove": "remove_subscription",
    "delete": "remove_subscription",
    "unsubscribe": "remove_subscription",
    "remove_subscription": "remove_subscription",
    "删除": "remove_subscription",
    "取消": "remove_subscription",
    "list": "list_subscriptions",
    "list_subscriptions": "list_subscriptions",
    "列表": "list_subscriptions",
    "accounts": "account_status",
    "account_status": "account_status",
    "账号": "account_status",
    "status": "check_status",
    "check_status": "check_status",
    "诊断": "check_status",
    "continue": "continue_pending",
    "continue_pending": "continue_pending",
    "cont": "continue_pending",
    "选": "continue_pending",
    "选择": "continue_pending",
    "确认": "continue_pending",
    "取消任务": "continue_pending",
}


CONFIRM_REPLIES = {
    "确认",
    "确定",
    "确认添加",
    "添加",
    "可以",
    "是",
    "是的",
    "好",
    "yes",
    "y",
    "ok",
    "okay",
    "add",
    "confirm",
}


CANCEL_REPLIES = {
    "取消",
    "放弃",
    "不添加",
    "不要",
    "不用",
    "否",
    "no",
    "n",
    "cancel",
    "stop",
}
