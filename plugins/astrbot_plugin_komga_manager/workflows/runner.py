from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .formatting import format_tool_payload, format_user_payload
from .models import READ_WORKFLOWS, WRITE_WORKFLOWS, WorkflowRequest
from .proposals import build_write_proposal
from .routing import route_natural_text


async def run_komga_workflow(
    plugin: Any,
    event: Any,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    if request.workflow == "ai_dispatch":
        text = str(request.params.get("text") or request.target or "")
        routed = route_natural_text(text, request.params)
        if routed is None:
            yield _reply(event, request, "请说明要查看书库、最近内容、搜索系列、查看详情或提交维护提案。")
            return
        routed.source = request.source
        request = routed

    if request.workflow in WRITE_WORKFLOWS:
        yield _payload_reply(event, request, build_write_proposal(request))
        return
    if request.workflow not in READ_WORKFLOWS:
        yield _reply(event, request, f"未知 Komga workflow: {request.workflow}")
        return

    try:
        result = await _run_read(plugin.client(), request, plugin.default_limit())
        payload = {
            "ok": True,
            "executed": True,
            "read_only": True,
            "operation": request.workflow,
            "result": result,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "executed": False,
            "read_only": True,
            "operation": request.workflow,
            "error": str(exc),
        }
    yield _payload_reply(event, request, payload)


async def _run_read(client: Any, request: WorkflowRequest, default_limit: int) -> Any:
    limit = _limit(request.params.get("limit"), default_limit)
    target = str(request.target or "").strip()
    params = request.params
    if request.workflow == "list_libraries":
        return await client.list_libraries()
    if request.workflow == "list_recent":
        return await client.list_recent(limit)
    if request.workflow == "search_series":
        query = str(params.get("query") or target).strip()
        return await client.search_series(query, limit)
    if request.workflow == "series_detail":
        return await client.series_detail(str(params.get("series_id") or target))
    if request.workflow == "list_books":
        return await client.list_books(str(params.get("series_id") or target), limit)
    if request.workflow == "on_deck":
        return await client.on_deck(limit)
    if request.workflow == "collections":
        return await client.collections(limit)
    if request.workflow == "readlists":
        return await client.readlists(limit)
    raise ValueError(f"unsupported read workflow: {request.workflow}")


def _payload_reply(event: Any, request: WorkflowRequest, payload: dict[str, Any]) -> Any:
    return _reply(
        event,
        request,
        format_tool_payload(payload) if request.source == "tool" else format_user_payload(payload),
    )


def _reply(event: Any, request: WorkflowRequest, text: str) -> Any:
    return text if request.source == "tool" else event.plain_result(text)


def _limit(value: Any, default: int) -> int:
    try:
        return max(1, min(int(value or default), 100))
    except (TypeError, ValueError):
        return default

