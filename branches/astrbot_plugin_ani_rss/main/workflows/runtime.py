from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..integrations.ani_rss import AniRssError
from ..ui.rendering import result_for_interaction
from .models import WorkflowRequest
from .utils import _first_text, _get_bool, _get_optional_bool


async def silent_connection_preflight(plugin: Any, workflow: str) -> str:
    if workflow in {"ai_dispatch", "check_status", "continue_pending"}:
        return ""
    try:
        await plugin.client().ping()
    except Exception as exc:
        logger.warning("ANI-RSS silent preflight failed before %s: %s", workflow, exc)
        return str(exc)
    return ""


def reply(event: AstrMessageEvent, request: WorkflowRequest, text: str) -> Any:
    if request.source == "tool":
        return text
    return event.plain_result(text)


async def interactive_reply(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    text: str,
    *,
    title: str = "",
) -> Any:
    result, path = await result_for_interaction(plugin, event, text, title=title)
    if path:
        request.rendered_cards.append(path)
    return result


def foreground_interaction_enabled(request: WorkflowRequest) -> bool:
    return request.source != "tool" or _get_bool(request.params, "interactive", default=False)


async def build_from_request(plugin: Any, request: WorkflowRequest) -> dict[str, Any]:
    params = request.params
    rss_url = _first_text({"target": request.target, **params}, "rss_url", "url", "target")
    if not rss_url:
        raise AniRssError("rss_url is required.")
    return await plugin.build_subscription(
        rss_url=rss_url,
        rss_type=_first_text(params, "rss_type", "type") or "auto",
        bgm_url=_first_text(params, "bgm_url", "bgmUrl", "bangumi_url"),
        subgroup=_first_text(params, "subgroup"),
        enable=_get_optional_bool(params, "enable"),
    )
