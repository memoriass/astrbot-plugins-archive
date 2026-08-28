from __future__ import annotations

from typing import Any

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .plugin.cache_store import PluginCacheMixin
from .plugin.pending_store import PendingTaskStoreMixin
from .plugin.preferences import PluginPreferenceMixin
from .plugin.settings import PluginSettingsMixin
from .plugin.subscription_builder import SubscriptionBuilderMixin
from .plugin.tool_results import PluginToolResultMixin
from .plugin.tooling import (
    apply_tool_prompt_flags,
    help_text,
    message_event_from_tool_arg,
)
from .routing.commands import (
    ANIRSS_COMMAND_NAMES,
    InvalidPendingShortcutFilter,
    PENDING_SHORTCUT_TEXT_KEY,
    PendingShortcutFilter,
    split_command_tail,
)
from .workflows import (
    format_workflow_list,
    run_ani_rss_workflow,
    workflow_from_cli,
    workflow_from_pending_shortcut,
    workflow_from_tool,
)


@register(
    "astrbot_plugin_ani_rss",
    "memoriass",
    "ANI-RSS 订阅管理插件，支持 Agent 通过 workflow 搜索并交互式添加订阅。",
    "1.1.1",
    "https://github.com/memoriass/astrbot_plugin_ani_rss",
)
class AniRssPlugin(
    PluginSettingsMixin,
    PendingTaskStoreMixin,
    PluginCacheMixin,
    PluginPreferenceMixin,
    SubscriptionBuilderMixin,
    PluginToolResultMixin,
    Star,
):
    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    async def initialize(self) -> None:
        self.runtime_store()
        self.cleanup_runtime_store()
        self.start_runtime_cleanup()

    async def terminate(self) -> None:
        self.cleanup_runtime_store()
        await self.stop_runtime_cleanup()

    @filter.llm_tool(name="ani_rss")
    async def ani_rss(
        self,
        event: Any,
        workflow: str,
        target: str = "",
        params: object = "",
    ):
        """ANI-RSS 订阅助手的自然语言 workflow 工具。

        当用户提到 ANI-RSS、Mikan、蜜柑、番剧订阅、追番、RSS 订阅、
        字幕组、搜索番剧、推荐番剧或添加订阅时，优先使用本工具。
        不要要求用户先检查连接；插件会在真实业务 workflow 开始前静默检测
        ANI-RSS API 连通性。

        常用 workflow：
        - ai_dispatch：自然语言或不完整参数的前置分流入口。
        - recommend_mikan_subscription：推荐本季或指定条件的 Mikan 候选。
        - add_mikan_subscription：按番名搜索 Mikan，选择番剧和字幕组后添加。
        - search_mikan：只搜索 Mikan 番剧或查看字幕组 RSS；AI 内部检索默认不主动发卡。
        - list_subscriptions：查看 ANI-RSS 已启用订阅列表。
        - refresh_all / refresh_subscription：刷新全部或指定订阅。
        - continue_pending：用户引用候选卡并回复序号、确认或取消时继续任务。

        Candidate and selection cards are non-blocking. The plugin returns
        a task id such as ani1a2b3c4d and stores the pending workflow state.
        Short unique prefixes or suffixes are accepted when they keep the
        `ani` prefix, such as ani3c4d.

        Args:
            workflow(string): One workflow scenario id, such as
                ai_dispatch, add_mikan_subscription, recommend_mikan_subscription,
                search_mikan, list_subscriptions, refresh_subscription,
                refresh_all, check_status, preview_subscription, or continue_pending.
            target(string): Natural text, anime title, RSS URL, Mikan URL,
                subscription id, or task id.
            params(object): Optional JSON object. Examples:
                {"query":"番名"}, {"limit":8,"min_score":7,"preview_only":true},
                {"subscription_id":"..."}, {"task_id":"ani1a2b3c4d","choice":"1"}.
        """
        request = workflow_from_tool(workflow, target, params)
        actual_event = message_event_from_tool_arg(event)
        apply_tool_prompt_flags(actual_event, request)
        async for item in run_ani_rss_workflow(self, actual_event, request):
            yield item

    @filter.custom_filter(PendingShortcutFilter)
    async def cmd_pending_shortcut(self, event: AstrMessageEvent):
        text = event.get_extra(PENDING_SHORTCUT_TEXT_KEY, event.get_message_str())
        request = workflow_from_pending_shortcut(text)
        if request is None:
            return
        async for item in run_ani_rss_workflow(self, event, request):
            yield item

    @filter.custom_filter(InvalidPendingShortcutFilter)
    async def cmd_invalid_pending_shortcut(self, event: AstrMessageEvent):
        example = self.command_example("ani68d2 1", event)
        yield event.plain_result(f"ANI-RSS 挂起任务命令格式已更新，请使用 `{example}`。")

    @filter.command("anirss", alias=set(ANIRSS_COMMAND_NAMES[1:]))
    async def cmd_anirss(
        self,
        event: AstrMessageEvent,
        workflow: str = "help",
        args: GreedyStr = GreedyStr,
    ):
        raw_workflow, raw_args = split_command_tail(event.get_message_str(), ANIRSS_COMMAND_NAMES)
        if raw_workflow:
            workflow, args = raw_workflow, raw_args

        if workflow in ("help", "h", "?"):
            yield event.plain_result(help_text(self, event) + "\n\n" + format_workflow_list())
            return

        request = workflow_from_cli(workflow, args)
        if request is None:
            yield event.plain_result(
                f"不支持的 ANI-RSS workflow：{workflow}。\n" + format_workflow_list(),
            )
            return

        async for item in run_ani_rss_workflow(self, event, request):
            yield item
