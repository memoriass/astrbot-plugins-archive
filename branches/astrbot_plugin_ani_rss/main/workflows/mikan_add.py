from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..integrations.ani_rss import AniRssError
from .formatting import format_mikan_candidates
from .mikan import (
    _enrich_mikan_candidate,
    _enrich_mikan_candidates_for_card,
    mikan_candidates,
)
from .mikan_fetch import fetch_mikan_search
from .mikan_selection import select_mikan_group
from .models import WorkflowRequest
from .pending import (
    pending_footer,
    pending_tool_summary,
    store_pending_rendered_cards,
    store_pending_task,
)
from .rss import run_add_subscription
from .runtime import foreground_interaction_enabled, interactive_reply, reply
from .utils import _first_text, _looks_like_rss_url


async def run_add_mikan_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    params = request.params
    rss_url = _first_text({"target": request.target, **params}, "rss_url", "url")
    if _looks_like_rss_url(rss_url):
        request.target = rss_url
        request.params["rss_type"] = "mikan"
        async for item in run_add_subscription(plugin, event, request):
            yield item
        return

    query = _first_text(
        {"target": request.target, **params},
        "query",
        "title",
        "name",
        "target",
    )
    mikan_url = _first_text(params, "mikan_url", "bangumi_url")
    if not query and not mikan_url:
        yield reply(event, request, "add_mikan_subscription 需要番名 query，或 mikan_url/rss_url。")
        return

    async for item in run_mikan_add_steps(plugin, event, request):
        yield item


async def run_mikan_add_steps(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        params = request.params
        mikan_url = _first_text(
            {"target": request.target, **params},
            "mikan_url",
            "bangumi_url",
        )
        candidate: dict[str, Any] | None = None
        if not mikan_url:
            query = _first_text(
                {"target": request.target, **params},
                "query",
                "title",
                "name",
                "target",
            )
            data = await fetch_mikan_search(plugin, query)
            candidates = mikan_candidates(data)
            if not candidates:
                yield reply(event, request, f"未搜索到 Mikan 番剧：{query}")
                return

            if len(candidates) == 1:
                candidate = candidates[0]
            else:
                shown = await _enrich_mikan_candidates_for_card(
                    plugin,
                    candidates[:8],
                )
                task_id, _task = store_pending_task(
                    plugin,
                    event,
                    request,
                    kind="select_mikan_anime",
                    payload={"candidates": shown},
                )
                body = format_mikan_candidates(
                    shown,
                    limit=8,
                    heading="Mikan 选择要订阅的番剧",
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
                return
            candidate = await _enrich_mikan_candidate(plugin, candidate)
            mikan_url = str(candidate.get("url") or "")
            if not mikan_url:
                yield reply(event, request, "所选 Mikan 番剧没有可用链接，无法继续添加。")
                return

        async for item in select_mikan_group(
            plugin,
            event,
            request,
            mikan_url,
            candidate=candidate,
        ):
            yield item
    except AniRssError as exc:
        yield reply(event, request, f"Mikan 添加 workflow 失败: {exc}")
    except Exception as exc:
        logger.exception("Unexpected Mikan add workflow failure")
        yield reply(event, request, f"Mikan 添加 workflow 失败: {exc}")
