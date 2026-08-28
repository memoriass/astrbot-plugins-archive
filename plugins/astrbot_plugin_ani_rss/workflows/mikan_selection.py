from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .duplicates import (
    find_enabled_duplicate_subscription,
    format_duplicate_subscription,
)
from .formatting import format_added, format_mikan_groups
from .mikan import _enrich_mikan_candidate, _groups_from_candidate
from .mikan_fetch import fetch_mikan_groups
from .models import WorkflowRequest
from .pending import (
    cleanup_task_cards,
    event_origin,
    extract_choice_index,
    pending_footer,
    pending_tool_summary,
    store_pending_rendered_cards,
    request_from_task,
    store_pending_task,
)
from .runtime import build_from_request, foreground_interaction_enabled, interactive_reply, reply


async def select_mikan_group(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    mikan_url: str,
    *,
    candidate: dict[str, Any] | None = None,
    task_id: str = "",
) -> AsyncIterator[Any]:
    if not mikan_url:
        yield reply(event, request, "Mikan 番剧 URL 为空，无法继续。")
        return

    if not candidate or not candidate.get("bgmUrl") or not candidate.get("groups"):
        candidate = await _enrich_mikan_candidate(plugin, candidate or {"url": mikan_url})

    groups = _groups_from_candidate(candidate)
    if not groups:
        groups = await fetch_mikan_groups(plugin, mikan_url)
    groups = [group for group in groups if str(group.get("rss") or "").strip()]
    if not groups:
        yield reply(event, request, "该 Mikan 番剧没有找到可用字幕组 RSS。")
        return
    groups = _rank_groups(plugin, event, groups)
    auto_group = _auto_select_group(plugin, event, groups)
    if auto_group:
        async for item in add_mikan_group_subscription(
            plugin,
            event,
            request,
            candidate=candidate or {},
            group=auto_group,
        ):
            yield item
        return

    shown_groups = groups[:8]
    task_id, _task = store_pending_task(
        plugin,
        event,
        request,
        kind="select_mikan_group",
        payload={
            "candidate": candidate or {},
            "groups": shown_groups,
            "mikan_url": mikan_url,
        },
        task_id=task_id,
    )
    body = format_mikan_groups(shown_groups, limit=8)
    if not foreground_interaction_enabled(request):
        yield reply(
            event,
            request,
            body + pending_tool_summary(plugin, event, task_id, "选 1"),
        )
        return
    result = await interactive_reply(
        plugin,
        event,
        request,
        body + pending_footer(plugin, event, task_id, "选 1"),
    )
    store_pending_rendered_cards(plugin, task_id, request)
    yield result


async def continue_select_mikan_anime(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    task_id: str,
    task: dict[str, Any],
    action: str,
) -> AsyncIterator[Any]:
    candidates = [item for item in task.get("candidates") or [] if isinstance(item, dict)]
    if not candidates:
        yield reply(event, request, f"任务 {task_id} 没有可用番剧候选。")
        return
    selected = extract_choice_index(action, len(candidates))
    if selected is None:
        yield reply(event, request, f"任务 {task_id} 等待选择番剧。请回复 1-{len(candidates)}，或回复“取消”。")
        return

    popped = plugin.pop_pending_task(task_id)
    cleanup_task_cards(popped)
    resumed_request = request_from_task(task, request.source)
    try:
        candidate = await _enrich_mikan_candidate(plugin, candidates[selected])
        mikan_url = str(candidate.get("url") or "")
        async for item in select_mikan_group(
            plugin,
            event,
            resumed_request,
            mikan_url,
            candidate=candidate,
            task_id=task_id,
        ):
            yield item
    except Exception as exc:
        logger.exception("Unexpected ANI-RSS pending Mikan anime selection failure")
        yield reply(event, request, f"继续 Mikan 番剧选择失败: {exc}")


async def continue_select_mikan_group(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    task_id: str,
    task: dict[str, Any],
    action: str,
) -> AsyncIterator[Any]:
    groups = [item for item in task.get("groups") or [] if isinstance(item, dict)]
    if not groups:
        yield reply(event, request, f"任务 {task_id} 没有可用字幕组候选。")
        return
    selected = extract_choice_index(action, len(groups))
    if selected is None:
        yield reply(event, request, f"任务 {task_id} 等待选择字幕组。请回复 1-{len(groups)}，或回复“取消”。")
        return

    popped = plugin.pop_pending_task(task_id)
    cleanup_task_cards(popped)
    _record_group_rejections(plugin, event, groups[:selected])
    group = groups[selected]
    rss_url = str(group.get("rss") or "")
    if not rss_url:
        yield reply(event, request, "所选字幕组没有 RSS 地址，无法添加。")
        return

    resumed_request = request_from_task(task, request.source)
    candidate = task.get("candidate") if isinstance(task.get("candidate"), dict) else {}
    async for item in add_mikan_group_subscription(
        plugin,
        event,
        resumed_request,
        candidate=candidate,
        group=group,
    ):
        yield item


async def add_mikan_group_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    *,
    candidate: dict[str, Any],
    group: dict[str, Any],
) -> AsyncIterator[Any]:
    rss_url = str(group.get("rss") or "")
    if not rss_url:
        yield reply(event, request, "所选字幕组没有 RSS 地址，无法添加。")
        return

    resumed_request = request
    resumed_request.target = rss_url
    resumed_request.params["rss_type"] = "mikan"
    resumed_request.params.setdefault("subgroup", str(group.get("label") or ""))
    bgm_url = str(group.get("bgmUrl") or candidate.get("bgmUrl") or "")
    if bgm_url:
        resumed_request.params.setdefault("bgm_url", bgm_url)
    try:
        ani = await build_from_request(plugin, resumed_request)
        duplicate = await find_enabled_duplicate_subscription(plugin, ani)
        if duplicate:
            text = format_duplicate_subscription(duplicate)
            if request.source == "tool":
                yield reply(event, request, text)
            else:
                yield await interactive_reply(plugin, event, request, text)
            return
        message = await plugin.client(require_api_key=True).add_ani(ani)
        invalidate = getattr(plugin, "invalidate_subscription_cache", None)
        if callable(invalidate):
            invalidate()
        _record_group_preference(plugin, event, group)
        ani["_message"] = message
        text = format_added(ani)
        if foreground_interaction_enabled(request):
            yield await interactive_reply(plugin, event, request, text)
        else:
            yield reply(event, request, text)
    except Exception as exc:
        logger.exception("Unexpected Mikan pending auto add failure")
        yield reply(event, request, f"添加订阅失败: {exc}")


def _rank_groups(
    plugin: Any,
    event: AstrMessageEvent,
    groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranker = getattr(plugin, "rank_mikan_groups_by_preferences", None)
    if not callable(ranker):
        return groups
    try:
        return ranker(event_origin(event), groups)
    except Exception as exc:
        logger.debug("Failed to rank Mikan groups by preferences: %s", exc)
        return groups


def _auto_select_group(
    plugin: Any,
    event: AstrMessageEvent,
    groups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    selector = getattr(plugin, "should_auto_select_mikan_group", None)
    if not callable(selector):
        return None
    try:
        selected = selector(event_origin(event), groups)
    except Exception as exc:
        logger.debug("Failed to auto select Mikan group by preferences: %s", exc)
        return None
    return selected if isinstance(selected, dict) else None


def _record_group_preference(
    plugin: Any,
    event: AstrMessageEvent,
    group: dict[str, Any],
) -> None:
    recorder = getattr(plugin, "record_mikan_group_preference", None)
    if not callable(recorder):
        return
    try:
        recorder(event_origin(event), group)
    except Exception as exc:
        logger.debug("Failed to record Mikan group preference: %s", exc)


def _record_group_rejections(
    plugin: Any,
    event: AstrMessageEvent,
    groups: list[dict[str, Any]],
) -> None:
    rejecter = getattr(plugin, "reject_mikan_group_preference", None)
    if not callable(rejecter):
        return
    origin = event_origin(event)
    for group in groups:
        if not group.get("_preference_score"):
            continue
        try:
            rejecter(origin, group)
        except Exception as exc:
            logger.debug("Failed to reject Mikan group preference: %s", exc)
