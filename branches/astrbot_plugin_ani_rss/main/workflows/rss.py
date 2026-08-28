from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..integrations.ani_rss import AniRssError
from .duplicates import (
    find_enabled_duplicate_subscription,
    format_duplicate_subscription,
)
from .formatting import format_added, format_ani_summary, format_preview
from .models import CONFIRM_REPLIES, WorkflowRequest
from .pending import (
    cleanup_task_cards,
    pending_footer,
    pending_tool_summary,
    store_pending_rendered_cards,
    store_pending_task,
)
from .runtime import build_from_request, foreground_interaction_enabled, interactive_reply, reply
from .utils import normalize_reply

PREVIEW_ITEMS_LIMIT = 8


async def run_add_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        ani = await build_from_request(plugin, request)
        duplicate = await find_enabled_duplicate_subscription(plugin, ani)
        if duplicate:
            yield await _duplicate_reply(plugin, event, request, duplicate)
            return
        body = "\n".join(
            [
                "待确认 ANI-RSS 订阅:",
                format_ani_summary(ani),
                "确认后仅提交到 ANI-RSS；下载路径、过滤规则和后续刷新由 ANI-RSS 处理。",
            ],
        )
    except AniRssError as exc:
        yield reply(event, request, f"ANI-RSS 添加流程启动失败: {exc}")
        return
    except Exception as exc:
        logger.exception("Unexpected ANI-RSS add workflow preparation failure")
        yield reply(event, request, f"ANI-RSS 添加流程启动失败: {exc}")
        return

    task_id, _task = store_pending_task(
        plugin,
        event,
        request,
        kind="confirm_add",
        payload={"ani": ani},
    )
    if not foreground_interaction_enabled(request):
        yield reply(
            event,
            request,
            body + pending_tool_summary(plugin, event, task_id, "确认"),
        )
        return
    result = await interactive_reply(
        plugin,
        event,
        request,
        body + pending_footer(plugin, event, task_id, "确认"),
    )
    store_pending_rendered_cards(plugin, task_id, request)
    yield result


async def continue_confirm_add(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    task_id: str,
    task: dict[str, Any],
    action: str,
) -> AsyncIterator[Any]:
    if normalize_reply(action) not in CONFIRM_REPLIES:
        yield reply(event, request, f"任务 {task_id} 等待确认。请回复“确认”添加，或回复“取消”放弃。")
        return

    popped = plugin.pop_pending_task(task_id)
    cleanup_task_cards(popped)
    ani = dict(task.get("ani") or {})
    if not ani:
        yield reply(event, request, f"任务 {task_id} 缺少订阅内容，无法添加。")
        return
    try:
        duplicate = await find_enabled_duplicate_subscription(plugin, ani)
        if duplicate:
            yield await _duplicate_reply(plugin, event, request, duplicate)
            return
        message = await plugin.client(require_api_key=True).add_ani(ani)
        invalidate = getattr(plugin, "invalidate_subscription_cache", None)
        if callable(invalidate):
            invalidate()
        ani["_message"] = message
        text = format_added(ani)
        if foreground_interaction_enabled(request):
            yield await interactive_reply(plugin, event, request, text)
        else:
            yield reply(event, request, text)
    except Exception as exc:
        logger.exception("Unexpected ANI-RSS pending add failure")
        yield reply(event, request, f"添加订阅失败: {exc}")


async def run_preview_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        ani = await build_from_request(plugin, request)
        preview = await plugin.client(require_api_key=True).preview_ani(ani)
        yield reply(event, request, format_preview(ani, preview, PREVIEW_ITEMS_LIMIT))
    except Exception as exc:
        yield reply(event, request, f"Preview failed: {exc}")


async def _duplicate_reply(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    duplicate: dict[str, Any],
) -> Any:
    text = format_duplicate_subscription(duplicate)
    if request.source == "tool":
        return reply(event, request, text)
    return await interactive_reply(plugin, event, request, text)
