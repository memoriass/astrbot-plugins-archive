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
from .rendering import HtmlRendererAdapter
from .scheduler import BilibiliScheduler
from .utils.resource import get_template_path
from .webapi import register_bilibili_web_apis
from .workflows import (
    BiliPendingShortcutFilter,
    PendingTaskStore,
    render_workflow_result,
    run_bili_workflow,
    workflow_from_pending_event,
)


@register(
    "astrbot_plugin_bilibili_push", "Aisidaka", "Bilibili 动态与直播推送", "1.2.6"
)
class BilibiliPush(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = load_plugin_config(context.get_config() or {})

        # 路径初始化
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

        # 获取插件配置
        config = self.config
        self.push_on_startup = config.push_on_startup
        self.check_interval = config.check_interval
        self.dynamic_check_interval = config.dynamic_check_interval
        self.live_check_interval = config.live_check_interval
        self.request_delay_sec = config.request_delay_sec
        self.request_jitter_sec = config.request_jitter_sec
        self.live_batch_size = config.live_batch_size
        self.risk_cooldown_sec = config.risk_cooldown_sec

        self.enable_link_parser = config.enable_link_parser
        self.search_cache_expiry_hours = config.search_cache_expiry_hours
        self.enable_ai_tools = config.enable_ai_tools
        self.ai_pending_timeout_sec = config.ai_pending_timeout_sec
        self.enable_ai_auto_select_candidates = config.enable_ai_auto_select_candidates
        self.ai_auto_select_confidence = config.ai_auto_select_confidence
        self.pending_store = PendingTaskStore(self, ttl_sec=self.ai_pending_timeout_sec)

        # 核心组件初始化
        self.db = DatabaseManager(self.data_dir / "data.db")
        self.parser = BilibiliParser()
        self.scheduler = BilibiliScheduler(
            db=self.db,
            check_interval=self.check_interval,
            dynamic_check_interval=self.dynamic_check_interval,
            live_check_interval=self.live_check_interval,
            request_delay_sec=self.request_delay_sec,
            request_jitter_sec=self.request_jitter_sec,
            live_batch_size=self.live_batch_size,
            push_on_startup=self.push_on_startup,
            on_new_post=self._handle_new_post,
            star=self,
        )

        # 渲染器与指令处理器初始化 (解耦)
        self.renderer = HtmlRendererAdapter(get_template_path())
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
        )
        self.ai_handler = AiToolHandler(self)
        self.runtime = PluginRuntime(self)
        self.runtime.init_resources()
        self.web_api = register_bilibili_web_apis(context, self)

    async def initialize(self):
        """插件启动入口"""
        await self.pending_store.ensure_loaded()
        await self.runtime.start()

    # --- 指令入口 ---

    @filter.command("添加b站订阅", alias={"bilibili 添加订阅", "add_bili_sub"})
    async def add_sub(self, event: AstrMessageEvent, uid: str):
        """添加动态订阅"""
        async for ret in self.sub_handler.add_subscription(event, uid, self.parser):
            yield ret

    @filter.command("添加b站直播", alias={"bilibili 添加直播", "add_bili_live"})
    async def add_live(self, event: AstrMessageEvent, uid: str):
        """添加直播订阅"""
        async for ret in self.sub_handler.add_live_subscription(
            event, uid, self.parser
        ):
            yield ret

    @filter.command("取消b站订阅", alias={"删除b站订阅", "del_bili_sub"})
    async def del_sub(self, event: AstrMessageEvent, uid: str):
        """取消动态订阅"""
        async for ret in self.sub_handler.remove_subscription(
            event, uid, "dynamic", self.parser
        ):
            yield ret

    @filter.command("取消b站直播", alias={"删除b站直播", "del_bili_live"})
    async def del_live(self, event: AstrMessageEvent, uid: str):
        """取消直播提醒"""
        async for ret in self.sub_handler.remove_subscription(
            event, uid, "live", self.parser
        ):
            yield ret

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
        """继续 Bilibili workflow pending task。"""
        request = workflow_from_pending_event(event)
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
        """Bilibili 推送插件的统一 workflow 工具。

        当用户提到 Bilibili、B站、UP 主、动态订阅、直播订阅、账号状态、
        搜索 UP、删除订阅或查看订阅时，优先使用本工具。
        模糊 UP 名称会生成候选 pending task，不会直接写入订阅。

        常用 workflow：
        - search_up：搜索 UP 主并返回候选。
        - add_subscription：按明确 UID 添加订阅；按关键词时生成候选任务。
        - remove_subscription：删除当前会话订阅。
        - list_subscriptions：查看当前会话订阅。
        - account_status：查看登录账号池状态。
        - check_status：诊断插件状态。
        - continue_pending：继续候选选择或确认添加。

        Args:
            workflow(string): workflow id，例如 search_up、add_subscription、
                remove_subscription、list_subscriptions、account_status、
                check_status、continue_pending。
            target(string): UID、关键词或 task id。
            params(object): 可选 JSON，例如 {"sub_type":"dynamic"}、
                {"sub_type":"live"}、{"task_id":"bili1a2b3c4d","choice":"1"}。
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
    async def bili_add_dynamic_sub_tool(self, event: AstrMessageEvent, uid: str) -> str:
        """添加 B站动态订阅。

        Args:
            uid(string): UP 主 UID。
        """
        return await self.ai_handler.add_subscription(event, uid, "dynamic")

    @filter.llm_tool(name="bili_add_live_sub")
    async def bili_add_live_sub_tool(self, event: AstrMessageEvent, uid: str) -> str:
        """添加 B站直播订阅。

        Args:
            uid(string): UP 主 UID。
        """
        return await self.ai_handler.add_subscription(event, uid, "live")

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
        """删除 B站订阅。

        Args:
            uid(string): UP 主 UID。
            sub_type(string): 订阅类型，dynamic 或 live。
        """
        return await self.ai_handler.remove_subscription(event, uid, sub_type)

    async def _handle_new_post(self, platform: str, target_id: str, msgs: list):
        """处理来自调度器的新动态/直播推送"""
        await self.runtime.handle_new_post(platform, target_id, msgs)

    async def terminate(self):
        """插件终止时回收浏览器资源"""
        await self.runtime.stop()
