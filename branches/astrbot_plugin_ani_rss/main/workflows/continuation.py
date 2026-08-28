from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .mikan_flow import continue_select_mikan_anime, continue_select_mikan_group
from .models import CANCEL_REPLIES, WorkflowRequest
from .pending import (
    cleanup_task_cards,
    resolve_pending_action,
    resolve_pending_task,
)
from .rss import continue_confirm_add
from .runtime import reply
from .utils import normalize_reply


async def run_continue_pending(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    task_id, task, error = resolve_pending_task(plugin, event, request)
    if error or not task_id or not task:
        yield reply(event, request, error or "无法解析 ANI-RSS 挂起任务。")
        return

    action = resolve_pending_action(event, request)
    if normalize_reply(action) in CANCEL_REPLIES:
        popped = plugin.pop_pending_task(task_id)
        cleanup_task_cards(popped)
        yield reply(event, request, f"已取消 ANI-RSS 挂起任务: {task_id}")
        return

    kind = str(task.get("kind") or "")
    if kind == "confirm_add":
        async for item in continue_confirm_add(plugin, event, request, task_id, task, action):
            yield item
        return
    if kind == "select_mikan_anime":
        async for item in continue_select_mikan_anime(plugin, event, request, task_id, task, action):
            yield item
        return
    if kind == "select_mikan_group":
        async for item in continue_select_mikan_group(plugin, event, request, task_id, task, action):
            yield item
        return

    yield reply(event, request, f"无法识别的 ANI-RSS 挂起任务类型: {kind or '(empty)'}")
