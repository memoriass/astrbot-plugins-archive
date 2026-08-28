from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
import json
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.message.message_event_result import MessageChain

from ..presentation.search_results import (
    finalize_search_response,
    normalize_search_result,
    recommendation_card_document,
)
from ..presentation.result_renderer import render_document_to_file
from ..web.routes import register_dashboard_routes
class PlanaPluginWebMixin:
    def _register_dashboard_apis(self) -> None:
        """Register active dashboard and compatibility web routes."""
        register_dashboard_routes(self)

    def _register_recall_tool(self) -> None:
        """Register Plana active recall as an LLM function tool."""
        self.context.add_llm_tools(PlanaRecallMemoryTool(self))

    def _register_native_search_tool(self) -> None:
        self.context.add_llm_tools(PlanaNativeSearchTool(self))

    async def _llm_tool_recall_memory(
        self,
        context=None,
        query: str = "",
        k: int | float | str | None = None,
        kind: str = "",
        reason: str = "",
        **kwargs,
    ) -> str:
        event = kwargs.get("event")
        if event is None:
            event = getattr(getattr(context, "context", None), "event", None)
        scope = getattr(event, "unified_msg_origin", "global") or "global"
        effective_query = str(query or reason or kwargs.get("reason") or "").strip()
        result = self.runtime.recall_memory(scope, effective_query, str(kind or ""), k)
        return json.dumps(result, ensure_ascii=False, default=_json_default)


def _event_from_tool_context(context: Any, kwargs: dict[str, Any]) -> Any:
    event = kwargs.get("event")
    if event is not None:
        return event
    return getattr(getattr(context, "context", None), "event", None)


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return str(value)


class PlanaRecallMemoryTool(FunctionTool):
    def __init__(self, plugin: PlanaPluginWebMixin) -> None:
        super().__init__(
            name="plana_recall_memory",
            description=(
                "Recall Plana Core long-term memory with fused episodic, "
                "semantic and concept routes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Short keywords for long-term memory recall; do not "
                            "paste the full user message."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional recall reason if query keywords are unclear.",
                    },
                    "k": {
                        "type": "number",
                        "description": "Maximum result count. Default is configured by Plana Core.",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional memory kind, such as user_preference or task_fact.",
                    },
                },
            },
        )
        self._plugin = plugin

    async def call(self, context: Any, **kwargs: Any) -> ToolExecResult:
        return await self._plugin._llm_tool_recall_memory(
            context=context,
            query=str(kwargs.get("query") or ""),
            k=kwargs.get("k"),
            kind=str(kwargs.get("kind") or ""),
            reason=str(kwargs.get("reason") or ""),
            event=_event_from_tool_context(context, kwargs),
        )


class PlanaNativeSearchTool(FunctionTool):
    def __init__(self, plugin: Any) -> None:
        super().__init__(
            name="web_search_searxng",
            description="Search the public web through the self-hosted Plana search gateway. Returns titles, URLs, and snippets with no side effects.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query."}},
                "required": ["query"],
            },
        )
        self._plugin = plugin

    async def call(self, context: Any, **kwargs: Any) -> str | None:
        query = str(kwargs.get("query") or "").strip()[:300]
        timeout = aiohttp.ClientTimeout(total=20, connect=4)
        payload: dict[str, Any] = {"ok": False, "error": "search_unavailable"}
        attempts = 0
        for attempt in range(2):
            attempts = attempt + 1
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        "http://192.168.1.202:8770/v1/search",
                        params={"q": query},
                    ) as response:
                        if response.status >= 500:
                            payload = {"ok": False, "error": f"http_{response.status}"}
                        else:
                            payload = await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                payload = {"ok": False, "error": type(exc).__name__}
            if not _retryable_search_failure(payload) or attempt > 0:
                break
            await asyncio.sleep(0.5)
        result = normalize_search_result(query, payload, attempts=attempts)
        event = _event_from_tool_context(context, kwargs)
        if event is not None:
            setattr(event, "_plana_search_result", result)
            setattr(event, "_plana_skip_response_memory", True)
        logger.info(
            "Plana native search result: status=%s attempts=%s items=%s reason=%s",
            result.get("status"),
            result.get("attempts"),
            len(result.get("items", [])),
            result.get("degraded_reason") or "none",
        )
        if event is not None:
            await self._deliver_result(event, result)
            return None
        return json.dumps(result, ensure_ascii=False)

    async def _deliver_result(self, event: Any, result: dict[str, Any]) -> None:
        text = finalize_search_response("", result)
        chain = MessageChain().message(text)
        rendered = False
        document = recommendation_card_document(event.get_message_str(), result)
        if document is not None:
            try:
                path = await render_document_to_file(document)
                chain.file_image(path)
                rendered = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana recommendation card skipped: %s", exc)
        setattr(event, "_plana_search_direct_delivery", True)
        await event.send(chain)
        event.stop_event()
        logger.info(
            "Plana search delivery: turn=%s status=%s attempts=%s sources=%s rendered=%s components=%s",
            getattr(event, "_plana_turn_id", ""),
            result.get("status"),
            result.get("attempts"),
            len(result.get("items", [])),
            rendered,
            ["Plain", "Image"] if rendered else ["Plain"],
        )


def _retryable_search_failure(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return False
    return str(payload.get("error") or "") in {
        "DDGSException",
        "ClientConnectorError",
        "ClientConnectorDNSError",
        "ClientConnectionError",
        "ConnectionTimeoutError",
        "ServerDisconnectedError",
        "SocketTimeoutError",
        "TimeoutError",
        "TimeoutException",
        "http_502",
        "http_503",
        "http_504",
    }
