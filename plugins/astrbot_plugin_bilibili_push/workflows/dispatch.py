from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent

from .branches import (
    build_dispatch_branches,
    format_dispatch_options,
    select_dispatch_branch,
)
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
from .models import WorkflowRequest
from .pending import run_continue_pending
from .results import WorkflowResult, ensure_workflow_result
from .search import run_search_up
from .semantic_dispatch import analyze_semantic_dispatch
from .subscription import run_add_subscription, run_remove_subscription
from .utils import first_text


NEXT_WORKFLOW_HANDLERS = {
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


async def run_ai_dispatch(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> WorkflowResult:
    text = _dispatch_text(request)
    branches = build_dispatch_branches(text, request.params)
    selected = await analyze_semantic_dispatch(
        plugin,
        event,
        text,
        request.params,
        branches=branches,
    )
    if selected is None:
        selected = select_dispatch_branch(branches, request.params)
    if not selected:
        return WorkflowResult(format_dispatch_options(branches))

    handler = NEXT_WORKFLOW_HANDLERS.get(selected.workflow)
    if handler is None:
        return WorkflowResult(f"分支 {selected.branch_id} 指向未支持的 workflow。")

    next_request = WorkflowRequest(
        workflow=selected.workflow,
        target=selected.target,
        params=dict(selected.params),
        source=request.source,
    )
    result = handler(plugin, event, next_request)
    if hasattr(result, "__await__"):
        result = await result
    return ensure_workflow_result(result)


def _dispatch_text(request: WorkflowRequest) -> str:
    payload = {"target": request.target, **request.params}
    return first_text(
        payload,
        "text",
        "message",
        "prompt",
        "query",
        "keyword",
        "target",
        "value",
    )
