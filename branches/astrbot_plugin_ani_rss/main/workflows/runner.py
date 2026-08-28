from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Callable

from astrbot.api.event import AstrMessageEvent

from .continuation import run_continue_pending
from .dispatch import run_ai_dispatch
from .formatting import format_workflow_list
from .manage import (
    run_check_status,
    run_list_subscriptions,
    run_refresh_all,
    run_refresh_subscription,
)
from .mikan_flow import (
    run_add_mikan_subscription,
    run_recommend_mikan_subscription,
    run_search_mikan,
)
from .models import COMPILED_WORKFLOWS, WorkflowRequest
from .rss import run_add_subscription, run_preview_subscription
from .runtime import reply, silent_connection_preflight
from .tool_result_trace import run_with_tool_result_trace
from .utils import _normalize_workflow

WorkflowHandler = Callable[[Any, AstrMessageEvent, WorkflowRequest], AsyncIterator[Any]]

WORKFLOW_HANDLERS: dict[str, WorkflowHandler] = {
    "add_subscription": run_add_subscription,
    "add_mikan_subscription": run_add_mikan_subscription,
    "recommend_mikan_subscription": run_recommend_mikan_subscription,
    "search_mikan": run_search_mikan,
    "preview_subscription": run_preview_subscription,
    "list_subscriptions": run_list_subscriptions,
    "refresh_subscription": run_refresh_subscription,
    "refresh_all": run_refresh_all,
    "check_status": run_check_status,
    "continue_pending": run_continue_pending,
}


async def run_ani_rss_workflow(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    request.workflow = _normalize_workflow(request.workflow)
    spec = COMPILED_WORKFLOWS.get(request.workflow)
    if spec is None:
        yield reply(event, request, "未知 ANI-RSS workflow。\n" + format_workflow_list())
        return

    if request.workflow == "ai_dispatch":
        async for item in run_ai_dispatch(plugin, event, request, WORKFLOW_HANDLERS):
            yield item
        return

    preflight_error = await silent_connection_preflight(plugin, request.workflow)
    if preflight_error:
        yield reply(
            event,
            request,
            f"ANI-RSS 服务暂时不可用，无法继续执行订阅工作流: {preflight_error}",
        )
        return

    handler = WORKFLOW_HANDLERS.get(request.workflow)
    if handler is None:
        yield reply(event, request, "workflow 已注册但尚未实现，请检查插件版本。")
        return

    async for item in run_with_tool_result_trace(plugin, event, request, handler):
        yield item
