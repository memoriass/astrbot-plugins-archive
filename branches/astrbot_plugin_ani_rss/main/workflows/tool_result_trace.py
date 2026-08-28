from __future__ import annotations

from collections.abc import AsyncIterator
import re
from typing import Any, Callable

from astrbot.api.event import AstrMessageEvent

from .models import WorkflowRequest
from .pending import event_origin

WorkflowHandler = Callable[[Any, AstrMessageEvent, WorkflowRequest], AsyncIterator[Any]]


async def run_with_tool_result_trace(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    handler: WorkflowHandler,
) -> AsyncIterator[Any]:
    snippets: list[str] = []
    try:
        async for item in handler(plugin, event, request):
            snippet = _item_snippet(item)
            if snippet:
                snippets.append(snippet)
            yield item
    except Exception as exc:
        _record_result(plugin, event, request, False, f"未处理异常: {exc}")
        raise
    else:
        summary = _summary_text(snippets, request)
        _record_result(plugin, event, request, _looks_success(summary), summary)


def _record_result(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    success: bool,
    summary: str,
) -> None:
    recorder = getattr(plugin, "record_workflow_tool_result", None)
    if not callable(recorder):
        return
    recorder(
        origin=event_origin(event),
        workflow=request.workflow,
        target=request.target,
        source=request.source,
        success=success,
        summary=summary,
        payload={
            "params": dict(request.params),
            "rendered_cards": list(request.rendered_cards),
        },
    )


def _item_snippet(item: Any) -> str:
    if isinstance(item, str):
        return _clean(item)
    return ""


def _summary_text(snippets: list[str], request: WorkflowRequest) -> str:
    if snippets:
        return _clean("\n".join(snippets))[:800]
    if request.rendered_cards:
        return f"已输出交互卡片 {len(request.rendered_cards)} 张。"
    return "workflow 已执行。"


def _looks_success(summary: str) -> bool:
    return not bool(
        re.search(
            r"失败|failed|error|exception|不可用|无法|不存在|未搜索到|没有符合",
            summary,
            re.IGNORECASE,
        ),
    )


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()
