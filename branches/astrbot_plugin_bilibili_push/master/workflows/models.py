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
    "ai_dispatch": CompiledWorkflow(
        "ai_dispatch",
        "AI 前置分流",
        "把自然语言或工具参数先分析为受控分支，再转入具体 Bilibili workflow。",
    ),
    "search_up": CompiledWorkflow(
        "search_up",
        "搜索 UP 主",
        "按关键词搜索 UP 主，返回候选和 pending task。",
    ),
    "add_subscription": CompiledWorkflow(
        "add_subscription",
        "添加订阅",
        "按明确 UID 或关键词生成确认任务，用户确认后添加动态或直播订阅。",
    ),
    "remove_subscription": CompiledWorkflow(
        "remove_subscription",
        "删除订阅",
        "定位当前会话订阅并生成确认任务，用户确认后删除。",
    ),
    "list_subscriptions": CompiledWorkflow(
        "list_subscriptions",
        "订阅列表",
        "列出当前会话订阅。",
    ),
    "list_all_subscriptions": CompiledWorkflow(
        "list_all_subscriptions",
        "全部订阅",
        "列出当前会话全部动态和直播订阅。",
    ),
    "list_live_subscriptions": CompiledWorkflow(
        "list_live_subscriptions",
        "直播订阅",
        "列出当前会话直播订阅。",
    ),
    "list_dynamic_subscriptions": CompiledWorkflow(
        "list_dynamic_subscriptions",
        "动态订阅",
        "列出当前会话动态订阅。",
    ),
    "find_subscription": CompiledWorkflow(
        "find_subscription",
        "查找订阅",
        "在当前会话订阅和历史别名内查找 UP。",
    ),
    "account_status": CompiledWorkflow(
        "account_status",
        "账号状态",
        "查看 Bilibili 登录账号池状态。",
    ),
    "diagnose_health": CompiledWorkflow(
        "diagnose_health",
        "健康诊断",
        "检查数据库、账号池、调度器和渲染器状态。",
        user_visible=False,
    ),
    "diagnose_resolver": CompiledWorkflow(
        "diagnose_resolver",
        "解析诊断",
        "查看 UP 解析、别名命中、搜索回退和歧义统计。",
    ),
    "check_live_current_group": CompiledWorkflow(
        "check_live_current_group",
        "检查当前群直播",
        "手动检查当前会话的直播订阅。",
    ),
    "check_live_all_groups": CompiledWorkflow(
        "check_live_all_groups",
        "检查全部群直播",
        "生成确认任务，确认后手动检查全部群直播订阅。",
    ),
    "check_status": CompiledWorkflow(
        "check_status",
        "诊断状态",
        "检查插件关键依赖和账号池状态。",
        user_visible=False,
    ),
    "continue_pending": CompiledWorkflow(
        "continue_pending",
        "继续任务",
        "继续搜索候选选择或确认添加。",
    ),
}


WORKFLOW_ALIASES = {
    "ai": "ai_dispatch",
    "ai_dispatch": "ai_dispatch",
    "dispatch": "ai_dispatch",
    "natural": "ai_dispatch",
    "assistant": "ai_dispatch",
    "助手": "ai_dispatch",
    "分流": "ai_dispatch",
    "路由": "ai_dispatch",
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
    "list_all": "list_all_subscriptions",
    "list_all_subscriptions": "list_all_subscriptions",
    "全部订阅": "list_all_subscriptions",
    "list_live": "list_live_subscriptions",
    "list_live_subscriptions": "list_live_subscriptions",
    "直播订阅": "list_live_subscriptions",
    "list_dynamic": "list_dynamic_subscriptions",
    "list_dynamic_subscriptions": "list_dynamic_subscriptions",
    "动态订阅": "list_dynamic_subscriptions",
    "find_subscription": "find_subscription",
    "find_sub": "find_subscription",
    "查订阅": "find_subscription",
    "accounts": "account_status",
    "account_status": "account_status",
    "账号": "account_status",
    "diagnose_health": "diagnose_health",
    "diagnose_resolver": "diagnose_resolver",
    "resolver": "diagnose_resolver",
    "解析诊断": "diagnose_resolver",
    "check_live_current_group": "check_live_current_group",
    "live_current": "check_live_current_group",
    "check_live": "check_live_current_group",
    "当前群直播检查": "check_live_current_group",
    "当前群检查": "check_live_current_group",
    "check_live_all_groups": "check_live_all_groups",
    "live_all": "check_live_all_groups",
    "全部群直播检查": "check_live_all_groups",
    "全部检查": "check_live_all_groups",
    "check_status": "check_status",
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


REMOVE_CONFIRM_REPLIES = {
    "确认",
    "确定",
    "确认删除",
    "删除",
    "移除",
    "退订",
    "可以",
    "是",
    "是的",
    "好",
    "yes",
    "y",
    "ok",
    "okay",
    "remove",
    "delete",
    "unsubscribe",
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
