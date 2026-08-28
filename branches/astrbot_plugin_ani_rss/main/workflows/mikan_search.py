from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .formatting import format_mikan_candidates, format_mikan_groups
from .mikan import _enrich_mikan_candidates_for_card, mikan_candidates
from .mikan_fetch import fetch_mikan_groups, fetch_mikan_search
from .models import WorkflowRequest
from .pending import pending_footer, store_pending_rendered_cards, store_pending_task
from .runtime import interactive_reply, reply
from .utils import _first_text, _get_bool, _looks_like_mikan_url


async def run_search_mikan(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    params = request.params
    render_interactive = request.source != "tool" or _get_bool(params, "interactive", default=False)
    preview_only = (
        _get_bool(params, "preview_only", default=False)
        or _get_bool(params, "dry_run", default=False)
        or not render_interactive
    )
    mikan_url = _first_text(
        {"target": request.target, **params},
        "mikan_url",
        "bangumi_url",
        "url",
        "target",
    )
    try:
        if _looks_like_mikan_url(mikan_url):
            groups = await fetch_mikan_groups(plugin, mikan_url)
            if not groups:
                yield reply(event, request, "未找到 Mikan 字幕组。")
                return

            shown_groups = groups[:8]
            if preview_only:
                yield reply(event, request, format_mikan_groups(shown_groups, limit=8))
                return

            task_id, _task = store_pending_task(
                plugin,
                event,
                request,
                kind="select_mikan_group",
                payload={
                    "candidate": {},
                    "groups": shown_groups,
                    "mikan_url": mikan_url,
                },
            )
            result = await interactive_reply(
                plugin,
                event,
                request,
                format_mikan_groups(shown_groups, limit=8)
                + pending_footer(plugin, event, task_id, "选 1"),
            )
            store_pending_rendered_cards(plugin, task_id, request)
            yield result
            return

        query = _first_text({"target": request.target, **params}, "query", "title", "target")
        if not query:
            yield reply(event, request, "search_mikan 需要 query 或 mikan_url。")
            return
        data = await fetch_mikan_search(plugin, query)
        candidates = mikan_candidates(data)
        if not candidates:
            yield reply(event, request, "未搜索到 Mikan 番剧。")
            return

        shown = await _enrich_mikan_candidates_for_card(plugin, candidates[:10])
        if preview_only:
            yield reply(event, request, format_mikan_candidates(shown, limit=10))
            return

        task_id, _task = store_pending_task(
            plugin,
            event,
            request,
            kind="select_mikan_anime",
            payload={"candidates": shown},
        )
        result = await interactive_reply(
            plugin,
            event,
            request,
            format_mikan_candidates(shown, limit=10)
            + pending_footer(plugin, event, task_id, "选 1"),
        )
        store_pending_rendered_cards(plugin, task_id, request)
        yield result
    except Exception as exc:
        yield reply(event, request, f"Mikan search failed: {exc}")
