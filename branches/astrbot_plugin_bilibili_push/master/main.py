from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .core.config import load_plugin_config
from .core.runtime import PluginRuntime
from .database.db_manager import DatabaseManager
from .handlers.ai_handler import AiToolHandler
from .handlers.link_handler import LinkParserHandler
from .handlers.login_handler import LoginHandler
from .handlers.search_handler import SearchHandler
from .handlers.subscription_handler import SubscriptionHandler
from .parser.bilibili_parser import BilibiliParser
from .parser.video_downloader import BilibiliVideoDownloader
from .rendering import HtmlRendererAdapter
from .scheduler import BilibiliScheduler
from .utils.resource import get_template_path
from .webapi import register_bilibili_web_apis
from .workflows import (
    BiliNaturalWorkflowFilter,
    BiliPendingShortcutFilter,
    PendingTaskStore,
    render_workflow_result,
    run_bili_workflow,
    workflow_from_natural_language,
    workflow_from_pending_event,
)
from .workflows.models import WorkflowRequest


@register(
    "astrbot_plugin_bilibili_push", "Aisidaka", "Bilibili 动态与直播推送", "1.2.25"
)
class BilibiliPush(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = load_plugin_config(context.get_config() or {})

        self.plugin_dir = Path(__file__).parent
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        self.data_dir = (
            Path(get_astrbot_data_path())
            / "plugin_data"
            / "astrbot_plugin_bilibili_push"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.data_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.bg_dir = self.data_dir / "backgrounds"
        self.bg_dir.mkdir(parents=True, exist_ok=True)
        self.avatar_cache_dir = self.data_dir / "image_cache" / "avatars"
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)

        config = self.config
        self.display_timezone = config.display_timezone
        self.push_on_startup = config.push_on_startup
        self.check_interval = config.check_interval
        self.dynamic_check_interval = config.dynamic_check_interval
        self.live_check_interval = config.live_check_interval
        self.request_delay_sec = config.request_delay_sec
        self.request_jitter_sec = config.request_jitter_sec
        self.live_batch_size = config.live_batch_size
        self.risk_cooldown_sec = config.risk_cooldown_sec

        self.enable_link_parser = config.enable_link_parser
        self.enable_parser_video_download = config.enable_parser_video_download
        self.search_cache_expiry_hours = config.search_cache_expiry_hours
        self.enable_ai_tools = config.enable_ai_tools
        self.ai_pending_timeout_sec = config.ai_pending_timeout_sec
        self.enable_ai_semantic_dispatch = config.enable_ai_semantic_dispatch
        self.ai_semantic_dispatch_confidence = config.ai_semantic_dispatch_confidence
        self.ai_semantic_dispatch_timeout_sec = config.ai_semantic_dispatch_timeout_sec
        self.enable_ai_candidate_analysis = config.enable_ai_candidate_analysis
        self.ai_candidate_analysis_confidence = config.ai_candidate_analysis_confidence
        self.ai_candidate_analysis_timeout_sec = config.ai_candidate_analysis_timeout_sec
        self.enable_ai_auto_select_candidates = config.enable_ai_auto_select_candidates
        self.ai_auto_select_confidence = config.ai_auto_select_confidence
        self.workflow_resolver_stats = {"counters": {}}
        self.pending_store = PendingTaskStore(self, ttl_sec=self.ai_pending_timeout_sec)

        self.db = DatabaseManager(self.data_dir / "data.db")
        self.parser = BilibiliParser(display_timezone=self.display_timezone)
        self.scheduler = BilibiliScheduler(
            db=self.db,
            check_interval=self.check_interval,
            dynamic_check_interval=self.dynamic_check_interval,
            live_check_interval=self.live_check_interval,
            request_delay_sec=self.request_delay_sec,
            request_jitter_sec=self.request_jitter_sec,
            live_batch_size=self.live_batch_size,
            display_timezone=self.display_timezone,
            push_on_startup=self.push_on_startup,
            on_new_post=self._handle_new_post,
            star=self,
        )

        self.renderer = HtmlRendererAdapter(
            get_template_path(),
            avatar_cache_dir=self.avatar_cache_dir,
        )
        self.sub_handler = SubscriptionHandler(
            context,
            self.db,
            self.bg_dir,
            renderer=self.renderer,
        )
        self.login_handler = LoginHandler(
            context,
            self.temp_dir,
            self.bg_dir,
            renderer=self.renderer,
        )
        self.search_handler = SearchHandler(
            context,
            self.bg_dir,
            renderer=self.renderer,
        )
        self.link_handler = LinkParserHandler(
            context,
            renderer=self.renderer,
            template_name="parser_bili",
            video_downloader=BilibiliVideoDownloader(
                self.temp_dir / "parser_videos",
                max_size_mb=config.parser_video_max_size_mb,
                timeout_sec=config.parser_video_download_timeout_sec,
            ),
            enable_video_download=self.enable_parser_video_download,
        )
        self.ai_handler = AiToolHandler(self)
        self.runtime = PluginRuntime(self)
        self.runtime.init_resources()
        self.web_api = register_bilibili_web_apis(context, self)

    async def initialize(self):
        """插件启动入口"""
        await self.pending_store.ensure_loaded()
        await self.runtime.start()

    @filter.command("添加b站订阅", alias={"bilibili 添加订阅", "add_bili_sub"})
    async def add_sub(self, event: AstrMessageEvent, target: str):
        """添加动态订阅"""
        yield await self._run_subscription_workflow(
            event,
            "add_subscription",
            target,
            sub_type="dynamic",
        )

    @filter.command("添加b站直播", alias={"bilibili 添加直播", "add_bili_live"})
    async def add_live(self, event: AstrMessageEvent, target: str):
        """添加直播订阅"""
        yield await self._run_subscription_workflow(
            event,
            "add_subscription",
            target,
            sub_type="live",
        )

    @filter.command("取消b站订阅", alias={"删除b站订阅", "del_bili_sub"})
    async def del_sub(self, event: AstrMessageEvent, target: str):
        """取消动态订阅"""
        yield await self._run_subscription_workflow(
            event,
            "remove_subscription",
            target,
            sub_type="dynamic",
        )

    @filter.command("取消b站直播", alias={"删除b站直播", "del_bili_live"})
    async def del_live(self, event: AstrMessageEvent, target: str):
        """取消直播提醒"""
        yield await self._run_subscription_workflow(
            event,
            "remove_subscription",
            target,
            sub_type="live",
        )

    async def _run_subscription_workflow(
        self,
        event: AstrMessageEvent,
        workflow: str,
        target: str,
        *,
        sub_type: str,
    ):
        request = WorkflowRequest(
            workflow=workflow,
            target=target,
            params={"query": target, "uid": target, "sub_type": sub_type},
            source="command",
        )
        result = await run_bili_workflow(self, event, request)
        return await render_workflow_result(event, self.renderer, result)

    @filter.command("b站订阅列表", alias={"bilibili 订阅列表", "list_bili_sub"})
    async def list_subs(self, event: AstrMessageEvent):
        """列出本会话的所有订阅"""
        async for ret in self.list_subscriptions(event):
            yield ret

    async def list_subscriptions(self, event: AstrMessageEvent):
        async for ret in self.sub_handler.list_subscriptions(event, self.scheduler):
            yield ret

    @filter.command("b站登录", alias={"bilibili 登录", "b站扫码"})
    async def login(self, event: AstrMessageEvent):
        """通过二维码登录 B 站账号"""
        async for ret in self.login_handler.handle_login(event):
            yield ret

    @filter.command("b站登录状态")
    async def status(self, event: AstrMessageEvent):
        """查看当前登录账号池状态"""
        async for ret in self.login_handler.handle_status(event):
            yield ret

    @filter.command("b站搜索", alias={"bilibili 搜索", "search_bili"})
    async def search(self, event: AstrMessageEvent, keyword: str):
        """在 B 站搜索 UP 主并获取 UID"""
        async for ret in self.search_handler.handle_search(event, keyword, self):
            yield ret

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_link(self, event: AstrMessageEvent):
        """自动感应链接并解析"""
        async for ret in self.link_handler.handle_links(
            event, self.parser, self.enable_link_parser
        ):
            yield ret

    @filter.custom_filter(BiliPendingShortcutFilter)
    async def bilibili_pending_shortcut(self, event: AstrMessageEvent):
        """继续待处理事项。"""
        request = workflow_from_pending_event(event)
        if request is None:
            return
        result = await run_bili_workflow(self, event, request)
        yield await render_workflow_result(event, self.renderer, result)

    @filter.custom_filter(BiliNaturalWorkflowFilter)
    async def bilibili_natural_workflow(self, event: AstrMessageEvent):
        request = workflow_from_natural_language(event.get_message_str())
        if request is None:
            return
        result = await run_bili_workflow(self, event, request)
        yield await render_workflow_result(event, self.renderer, result)

    @filter.llm_tool(name="bili_workflow")
    async def bili_workflow_tool(
        self,
        event: AstrMessageEvent,
        workflow: str,
        target: str = "",
        params: object = "",
    ) -> str:
        """Bilibili 统一 workflow 工具。

        不确定意图时传 `ai_dispatch`。写操作只生成确认任务，不直接改订阅。

        Args:
            workflow(string): workflow id；可留空或传 ai_dispatch。
            target(string): UID、关键词或待处理事项引用。
            params(object): 可选 JSON，如 sub_type、choice、present。
        """
        return await self.ai_handler.run_workflow(event, workflow, target, params)

    @filter.llm_tool(name="bili_search_up")
    async def bili_search_up_tool(self, event: AstrMessageEvent, keyword: str) -> str:
        """搜索 B站 UP 主并返回 UID 列表。

        Args:
            keyword(string): 搜索关键词。
        """
        return await self.ai_handler.search_up(event, keyword)

    @filter.llm_tool(name="bili_add_dynamic_sub")
    async def bili_add_dynamic_sub_tool(self, event: AstrMessageEvent, target: str) -> str:
        """添加 B站动态订阅。target 可以是明确 UID 或 UP 主关键词，写入前需要用户确认。

        Args:
            target(string): UP 主 UID 或搜索关键词。
        """
        return await self.ai_handler.add_subscription(event, target, "dynamic")

    @filter.llm_tool(name="bili_add_live_sub")
    async def bili_add_live_sub_tool(self, event: AstrMessageEvent, target: str) -> str:
        """添加 B站直播订阅。target 可以是明确 UID 或 UP 主关键词，写入前需要用户确认。

        Args:
            target(string): UP 主 UID 或搜索关键词。
        """
        return await self.ai_handler.add_subscription(event, target, "live")

    @filter.llm_tool(name="bili_list_subs")
    async def bili_list_subs_tool(
        self,
        event: AstrMessageEvent,
        placeholder: str = "",
    ) -> str:
        """列出当前会话的 B站订阅。

        Args:
            placeholder(string): 预留参数，可留空。
        """
        return await self.ai_handler.list_subscriptions(event)

    @filter.llm_tool(name="bili_remove_sub")
    async def bili_remove_sub_tool(
        self,
        event: AstrMessageEvent,
        uid: str,
        sub_type: str,
    ) -> str:
        """删除 B站订阅。会先生成删除确认任务，用户确认后才会移除。

        Args:
            uid(string): UP 主 UID、已确认简称或当前订阅名称。
            sub_type(string): 订阅类型，dynamic、live 或 both。
        """
        return await self.ai_handler.remove_subscription(event, uid, sub_type)

    async def _handle_new_post(self, platform: str, target_id: str, msgs: list):
        """处理来自调度器的新动态/直播推送"""
        await self.runtime.handle_new_post(platform, target_id, msgs)

    async def terminate(self):
        """插件终止时回收浏览器资源"""
        await self.runtime.stop()
