from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .branches import (
    build_dispatch_branches,
    format_dispatch_options,
    select_dispatch_branch,
)
from .models import WorkflowRequest
from .runtime import reply, silent_connection_preflight
from .tool_result_trace import run_with_tool_result_trace
from .utils import _first_text


async def run_ai_dispatch(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    handlers: dict[str, Any],
) -> AsyncIterator[Any]:
    text = _dispatch_text(request)
    branches = build_dispatch_branches(text, request.params)
    selected = select_dispatch_branch(branches, request.params)
    if not selected:
        yield reply(event, request, format_dispatch_options(branches))
        return

    handler = handlers.get(selected.workflow)
    if handler is None or selected.workflow == request.workflow:
        yield reply(event, request, f"分支 {selected.branch_id} 指向未支持的 workflow。")
        return

    preflight_error = await silent_connection_preflight(plugin, selected.workflow)
    if preflight_error:
        yield reply(
            event,
            request,
            f"ANI-RSS 服务暂时不可用，无法继续执行订阅工作流: {preflight_error}",
        )
        return

    next_request = WorkflowRequest(
        workflow=selected.workflow,
        target=selected.target,
        params=dict(selected.params),
        source=request.source,
    )
    async for item in run_with_tool_result_trace(plugin, event, next_request, handler):
        yield item


def _dispatch_text(request: WorkflowRequest) -> str:
    payload = {"target": request.target, **request.params}
    return _first_text(
        payload,
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
