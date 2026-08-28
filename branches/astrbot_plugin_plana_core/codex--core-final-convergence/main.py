from __future__ import annotations

import asyncio

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr

from .dialogue import DialogueService
from .dialogue.entry_filters import (
    PlanaActiveTurnFilter,
    PlanaPassiveObserveFilter,
    get_active_plugin,
    set_active_plugin,
)
from .plugin.config import normalize_plana_config
from .plugin.build_info import build_info
from .plugin.livingmemory_compat import livingmemory_compat_text
from .plugin.plugin_bridge import PlanaPluginBridgeMixin
from .plugin.plugin_lifecycle import PlanaPluginLifecycleMixin
from .plugin.plugin_events import PlanaPluginEventMixin
from .plugin.plugin_web import PlanaPluginWebMixin
from .plugin.runtime import PlanaRuntime
from .plugin.webhook_governance import WebhookGovernanceService
from .presentation.gallery_context import GalleryContextPolicy
from .presentation.gallery_telemetry import GalleryDecisionTelemetry, GalleryReactionState
from .web import PlanaWebAPI
from .web.routes import guard_plugin_handler


class PlanaCorePlugin(
    PlanaPluginEventMixin,
    PlanaPluginLifecycleMixin,
    PlanaPluginBridgeMixin,
    PlanaPluginWebMixin,
    Star,
):
    """Plana persona, memory, state and tool runtime plugin."""

    _SESSION_PLUGIN_NAMES = ("astrbot_plugin_plana_core", "Plana Core")

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self._terminating = False
        self.raw_config = config
        self.config = normalize_plana_config(config)
        data_dir = StarTools.get_data_dir("astrbot_plugin_plana_core")
        self.runtime = PlanaRuntime(data_dir, self.config, astr_context=context)
        self.runtime.build_info = build_info()
        self.webhook_governance_service = WebhookGovernanceService(self.runtime)
        self.runtime.webhook_governance = self.webhook_governance_service
        self.dialogue = DialogueService(self.runtime)
        self.bridge_api_token = str(self.config.get("bridge_api_token", ""))
        self.enable_bridge_api = bool(self.config.get("enable_bridge_api", False))
        self.enable_web_dashboard = bool(self.config.get("enable_web_dashboard", True))
        self.enable_auto_maintenance = bool(
            self.config.get("enable_auto_maintenance", False)
        )
        self.auto_maintenance_interval = int(
            self.config.get("auto_maintenance_interval_hours", 6)
        )
        self.quiet_hours: str = str(self.config.get("quiet_hours", "") or "")
        self._quiet_hours_active: bool = False
        self._passive_observe_tasks: set[asyncio.Task] = set()
        self._tool_progress_tasks: dict[str, asyncio.Task] = {}
        self._gallery_state = GalleryReactionState(self.runtime.storage.db)
        self._gallery_context = GalleryContextPolicy(self.config, self._gallery_state)
        self._gallery_telemetry = GalleryDecisionTelemetry(self.runtime.storage.db)
        self._web_api: PlanaWebAPI | None = None

    async def initialize(self) -> None:
        try:
            self.runtime.initialize()
            self.webhook_governance_service.initialize()
            if self.runtime.enabled and self.enable_bridge_api:
                for route, handler, methods, desc in (
                    (
                        "/plana_core/bridge/state",
                        self._api_bridge_state,
                        ["GET"],
                        "Plana Core controlled bridge state endpoint",
                    ),
                    (
                        "/plana_core/bridge/payload",
                        self._api_bridge_payload,
                        ["POST"],
                        "Plana Core controlled bridge payload endpoint",
                    ),
                    (
                        "/plana_core/bridge/proactive/poll",
                        self._api_bridge_proactive_poll,
                        ["POST"],
                        "Plana Core controlled proactive pickup endpoint",
                    ),
                    (
                        "/plana_core/bridge/proactive/deliver",
                        self._api_bridge_proactive_deliver,
                        ["POST"],
                        "Plana Core controlled proactive delivery mark endpoint",
                    ),
                ):
                    self.context.register_web_api(
                        route,
                        guard_plugin_handler(self, handler),
                        methods,
                        desc,
                    )
            if self.enable_web_dashboard:
                self._web_api = PlanaWebAPI(
                    self.runtime,
                    provider_getter=self.context.get_using_provider,
                )
                self._register_dashboard_apis()
            if self.runtime.enabled and self.enable_auto_maintenance:
                self.runtime.job_manager.register(
                    "maintenance",
                    self._maintenance_cycle,
                    interval_seconds=max(1, self.auto_maintenance_interval) * 3600,
                    enabled=True,
                )
                self.runtime.job_manager.start_all()
                logger.info(
                    "Plana auto-maintenance enabled: interval=%dh",
                    self.auto_maintenance_interval,
                )
            if self.runtime.enabled:
                if self.runtime.enable_recall_tool:
                    self._register_recall_tool()
                self._register_native_search_tool()
                set_active_plugin(self)
        except Exception:
            self._terminating = True
            await self.runtime.job_manager.stop_all()
            for tool_name in (
                "plana_recall_memory",
                "web_search_searxng",
            ):
                self._remove_llm_tool(tool_name)
            if get_active_plugin() is self:
                set_active_plugin(None)
            raise
        logger.info(
            "Plana core initialized: version=%s build=%s enabled=%s bridge_api=%s web_dashboard=%s",
            self.runtime.build_info["version"],
            self.runtime.build_info["build_id"],
            self.runtime.enabled,
            self.enable_bridge_api,
            self.enable_web_dashboard,
        )
        if not self.runtime.enabled:
            logger.info(
                "Plana core is disabled; message filters, tools, bridge and jobs are inactive."
            )

    @filter.custom_filter(PlanaPassiveObserveFilter, False, priority=-100)
    async def passive_observe_message(self, event: AstrMessageEvent):
        return await self._handle_passive_observe_message(event)

    @filter.custom_filter(PlanaActiveTurnFilter, False, priority=20)
    async def on_active_message(self, event: AstrMessageEvent):
        async for result in self._handle_active_message(event):
            yield result

    @filter.on_waiting_llm_request(priority=20)
    async def on_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        await self._handle_waiting_llm_request(event)

    @filter.on_llm_request(priority=-100)
    async def on_llm_request(self, event: AstrMessageEvent, request_obj) -> None:
        await self._handle_llm_request(event, request_obj)

    @filter.on_llm_response(priority=20)
    async def on_llm_response(self, event: AstrMessageEvent, response) -> None:
        await self._handle_llm_response(event, response)

    @filter.after_message_sent(priority=20)
    async def after_message_sent(self, event: AstrMessageEvent) -> None:
        await self._handle_after_message_sent(event)

    @filter.on_using_llm_tool(priority=20)
    async def on_using_llm_tool(self, event: AstrMessageEvent, tool, tool_args) -> None:
        await self._handle_using_llm_tool(event, tool, tool_args)

    @filter.on_llm_tool_respond(priority=20)
    async def on_llm_tool_respond(
        self,
        event: AstrMessageEvent,
        tool,
        tool_args,
        tool_result,
    ) -> None:
        await self._handle_llm_tool_respond(event, tool, tool_args, tool_result)

    @filter.command("plana")
    async def plana(
        self, event: AstrMessageEvent, action: str = "status", value: GreedyStr = ""
    ):
        """Simplified Plana command; see /plana help for details."""
        action = action.strip().lower()
        value = str(value).strip()
        if action == "status":
            yield event.plain_result(self.runtime.status_text())
            return
        if action == "mode":
            if not self.runtime.set_mode(value):
                yield event.plain_result(
                    "mode must be one of: standby/observing/tasking/checking/"
                    "risk_review/waiting_confirm/reporting/handoff_to_bridge/silent"
                )
                return
            yield event.plain_result(f"Plana mode updated: {value}")
            return
        if action == "search":
            yield event.plain_result(self.runtime.search_text(event, value))
            return
        if action == "remember":
            yield event.plain_result(self.runtime.remember_text(event, value))
            return
        # -- help / fallback --
        yield event.plain_result(
            "Plana Core commands:\n"
            "  /plana            - 状态概览\n"
            "  /plana mode <m>   - 切换模式\n"
            "  /plana search <q> - 搜索记忆\n"
            "  /plana remember <text> - 记住事实\n"
            "  /plana help       - 显示此帮助\n"
            "管理面板: /api/plug/plana/dashboard"
        )

    @filter.command("lmem")
    async def lmem(
        self, event: AstrMessageEvent, action: str = "status", value: GreedyStr = ""
    ):
        """LivingMemory-compatible command facade backed by Plana services."""
        text = await livingmemory_compat_text(
            self.runtime,
            event,
            action,
            str(value),
            provider=self.context.get_using_provider(),
        )
        yield event.plain_result(text)
