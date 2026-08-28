from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..integrations.ani_rss import AniRssError
from .formatting import format_mikan_recommendations
from .mikan import (
    _mikan_season_payload,
    _rank_mikan_candidates,
    mikan_candidates,
)
from .mikan_fetch import fetch_mikan_search
from .models import WorkflowRequest
from .pending import (
    pending_footer,
    pending_tool_summary,
    store_pending_rendered_cards,
    store_pending_task,
)
from .runtime import foreground_interaction_enabled, interactive_reply, reply
from .utils import _first_text, _get_bool, _get_float, _get_int

DEFAULT_RECOMMEND_LIMIT = 8
DEFAULT_RECOMMEND_MIN_SCORE = 0.0
DEFAULT_RECOMMEND_INCLUDE_EXISTING = False


async def run_recommend_mikan_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    params = request.params
    query = _first_text({"target": request.target, **params}, "query", "title", "name", "target")
    limit = _get_int(
        params,
        "limit",
        default=DEFAULT_RECOMMEND_LIMIT,
    )
    min_score = _get_float(
        params,
        "min_score",
        default=DEFAULT_RECOMMEND_MIN_SCORE,
    )
    include_existing = _get_bool(
        params,
        "include_existing",
        default=DEFAULT_RECOMMEND_INCLUDE_EXISTING,
    )
    preview_only = _get_bool(
        params,
        "preview_only",
        default=False,
    ) or _get_bool(
        params,
        "dry_run",
        default=False,
    )
    if _get_bool(params, "interactive", default=False):
        preview_only = False
    payload = _mikan_season_payload(params)

    try:
        data = await fetch_mikan_search(plugin, query, payload)
        candidates = mikan_candidates(data)
        candidates = _rank_mikan_candidates(
            candidates,
            min_score=min_score,
            include_existing=include_existing,
        )
        if not candidates:
            yield reply(
                event,
                request,
                "没有符合条件的 Mikan 推荐结果。"
                f"\nquery={query or '(当前季度)'} min_score={min_score:g}"
                f" include_existing={include_existing}",
            )
            return

        shown = candidates[: max(limit, 1)]
        body = format_mikan_recommendations(
            shown,
            total=len(candidates),
            query=query,
            season=payload,
        )
        if preview_only:
            yield reply(event, request, body)
            return

        task_id, _task = store_pending_task(
            plugin,
            event,
            request,
            kind="select_mikan_anime",
            payload={"candidates": shown},
        )
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
    except AniRssError as exc:
        yield reply(event, request, f"Mikan 推荐 workflow 失败: {exc}")
    except Exception as exc:
        logger.exception("Unexpected Mikan recommend workflow failure")
        yield reply(event, request, f"Mikan 推荐 workflow 失败: {exc}")
