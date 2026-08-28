from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .dispatch import run_ai_dispatch
from .formatting import format_workflow_list
from .manage import (
    run_account_status,
    run_check_live_all_groups,
    run_check_live_current_group,
    run_check_status,
    run_diagnose_health,
    run_diagnose_resolver,
    run_find_subscription,
    run_list_all_subscriptions,
    run_list_dynamic_subscriptions,
    run_list_live_subscriptions,
    run_list_subscriptions,
)
from .models import COMPILED_WORKFLOWS, WorkflowRequest
from .pending import run_continue_pending
from .results import WorkflowResult, ensure_workflow_result
from .search import run_search_up
from .subscription import run_add_subscription, run_remove_subscription
from .utils import normalize_workflow


WorkflowHandler = Callable[[Any, AstrMessageEvent, WorkflowRequest], Awaitable[Any] | Any]


WORKFLOW_HANDLERS: dict[str, WorkflowHandler] = {
    "ai_dispatch": run_ai_dispatch,
    "search_up": run_search_up,
    "add_subscription": run_add_subscription,
    "remove_subscription": run_remove_subscription,
    "list_subscriptions": run_list_subscriptions,
    "list_all_subscriptions": run_list_all_subscriptions,
    "list_live_subscriptions": run_list_live_subscriptions,
    "list_dynamic_subscriptions": run_list_dynamic_subscriptions,
    "find_subscription": run_find_subscription,
    "account_status": run_account_status,
    "diagnose_health": run_diagnose_health,
    "diagnose_resolver": run_diagnose_resolver,
    "check_live_current_group": run_check_live_current_group,
    "check_live_all_groups": run_check_live_all_groups,
    "check_status": run_check_status,
    "continue_pending": run_continue_pending,
}


async def run_bili_workflow(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> WorkflowResult:
    request.workflow = normalize_workflow(request.workflow)
    if request.workflow not in COMPILED_WORKFLOWS:
        return WorkflowResult("未知 Bilibili workflow。\n" + format_workflow_list())

    handler = WORKFLOW_HANDLERS.get(request.workflow)
    if handler is None:
        return WorkflowResult("workflow 已注册但尚未实现。")

    result = handler(plugin, event, request)
    if hasattr(result, "__await__"):
        result = await result
    return ensure_workflow_result(result)
