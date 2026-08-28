from __future__ import annotations

from typing import Any

from astrbot.core.agent.tool import FunctionTool, ToolExecResult

from .capability import ActionEnvelope, CapabilityError
from .domain_routing import route_qbittorrent_read


class DomainToolMixin:
    def _register_domain_tools(self) -> None:
        self.context.add_llm_tools(QbittorrentDomainTool(self))

    def _unregister_domain_tools(self) -> None:
        unregister = getattr(self.context, "unregister_llm_tool", None)
        if not callable(unregister):
            return
        unregister("plana_qbittorrent")

    async def _plana_qbittorrent_read(self, query: str) -> dict[str, Any]:
        return await self._run_domain_read(
            "qbittorrent.production",
            route_qbittorrent_read(query),
        )

    async def _run_domain_read(self, service_ref: str, decision: Any) -> dict[str, Any]:
        if decision.clarification:
            return {
                "ok": False,
                "clarification": decision.clarification,
                "executed": False,
            }
        try:
            result = await self.capability_registry.execute(
                ActionEnvelope(
                    service_ref,
                    decision.capability,
                    decision.arguments,
                    "",
                )
            )
        except CapabilityError as exc:
            return {"ok": False, "error": str(exc), "executed": False}
        return {"ok": True, "executed": True, "result": result}


class QbittorrentDomainTool(FunctionTool):
    def __init__(self, plugin: DomainToolMixin) -> None:
        super().__init__(
            name="plana_qbittorrent",
            description="Route one natural-language qBittorrent read without exposing capability names.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's complete natural wording.",
                    }
                },
                "required": ["query"],
            },
        )
        self.plugin = plugin

    async def call(self, context: Any, **kwargs: Any) -> ToolExecResult:
        _ = context
        return await self.plugin._plana_qbittorrent_read(str(kwargs.get("query") or ""))
