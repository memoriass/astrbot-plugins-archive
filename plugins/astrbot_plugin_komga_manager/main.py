from __future__ import annotations

from typing import Any

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .plugin.settings import PluginSettingsMixin
from .plugin.tooling import help_text, iter_tool_outputs, message_event_from_tool_arg
from .workflows import run_komga_workflow, workflow_from_cli, workflow_from_tool


@register(
    "astrbot_plugin_komga_manager",
    "memoriass",
    "Komga 只读查询与受控维护提案插件。",
    "0.1.0",
    "https://github.com/memoriass/astrbot_plugin_komga_manager",
)
class KomgaManagerPlugin(PluginSettingsMixin, Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = dict(config or {})

    async def terminate(self) -> None:
        await self.close_client()

    @filter.llm_tool(name="komga_manager")
    async def komga_manager(
        self,
        event: Any,
        workflow: str,
        target: str = "",
        params: object = "",
    ):
        """Query Komga or create a governed maintenance proposal.

        Read workflows execute immediately: ai_dispatch, list_libraries,
        list_recent, search_series, series_detail, list_books, on_deck,
        collections, and readlists.

        Write workflows never execute Komga mutations. scan_library,
        analyze_library, refresh_library_metadata, and
        refresh_series_metadata only return action=write_pending with
        requires_confirmation=true.

        Args:
            workflow(string): One workflow id. Use ai_dispatch for natural text.
            target(string): Natural wording, search query, library id, or series id.
            params(object): Optional JSON object with query, limit, library_id, or series_id.
        """
        request = workflow_from_tool(workflow, target, params)
        actual_event = message_event_from_tool_arg(event)
        outputs = run_komga_workflow(self, actual_event, request)
        async for item in iter_tool_outputs(actual_event, outputs):
            yield item

    @filter.command("komga")
    async def cmd_komga(
        self,
        event: AstrMessageEvent,
        workflow: str = "help",
        args: GreedyStr = GreedyStr,
    ):
        if workflow in {"help", "h", "?"}:
            yield event.plain_result(help_text())
            return
        request = workflow_from_cli(workflow, str(args or ""))
        if request is None:
            yield event.plain_result("未知 Komga workflow。\n" + help_text())
            return
        async for item in run_komga_workflow(self, event, request):
            yield item

