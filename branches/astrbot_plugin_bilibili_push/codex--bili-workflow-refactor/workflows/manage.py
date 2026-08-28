from __future__ import annotations

from ..core.http import HttpClient
from .cards import account_status_card, subscription_list_card
from .formatting import format_accounts, format_subscriptions, format_workflow_list
from .models import WorkflowRequest
from .results import WorkflowResult
from .runtime import event_origin


async def run_list_subscriptions(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    subscriptions = plugin.db.get_subscriptions(event_origin(event))
    text = format_subscriptions(subscriptions)
    if not subscriptions:
        return WorkflowResult(text)
    return WorkflowResult(text, cards=[await subscription_list_card(plugin, subscriptions)])


async def run_account_status(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    accounts = await HttpClient.get_accounts()
    current_index = getattr(HttpClient, "_current_account_index", 0)
    text = format_accounts(accounts, current_index)
    if not accounts:
        return WorkflowResult(text)
    return WorkflowResult(text, cards=[account_status_card(accounts, current_index)])


async def run_check_status(plugin, event, request: WorkflowRequest) -> str:
    accounts = await HttpClient.get_accounts()
    browser_ready = "已配置系统 Chrome 回退" if hasattr(plugin, "renderer") else "未知"
    return (
        "Bilibili 插件诊断：\n"
        f"- workflows: 已启用\n"
        f"- LLM tools: bili_workflow + 能力说明工具\n"
        f"- accounts: {len(accounts)}\n"
        f"- renderer: {browser_ready}\n\n"
        + format_workflow_list()
    )
