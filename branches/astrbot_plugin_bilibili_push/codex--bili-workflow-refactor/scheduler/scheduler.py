"""调度器模块"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

from ..core.types import MessageSegment
from ..database.db_manager import DatabaseManager, Subscription
from ..dynamic.bilibili import BilibiliDynamic
from ..live.bilibili import BilibiliLive
from ..utils.html_renderer import BrowserManager, HtmlRenderer
from ..utils.logger import logger
from ..utils.renderers.dynamic_card import DynamicCardTheme
from ..utils.renderers.movie_card import MovieCardTheme
from ..utils.resource import get_template_path
from .dispatcher import PostDispatcher
from .dynamic_checker import DynamicSubscriptionChecker
from .live_checker import LiveSubscriptionChecker
from .subscription_group import group_subscriptions


class BilibiliScheduler:
    def __init__(
        self,
        db: DatabaseManager,
        check_interval: int = 30,
        dynamic_check_interval: int | None = None,
        live_check_interval: int | None = None,
        request_delay_sec: float = 0.8,
        request_jitter_sec: float = 5.0,
        live_batch_size: int = 50,
        push_on_startup: bool = False,
        on_new_post: Callable[[str, str, list[MessageSegment]], Awaitable[None]]
        | None = None,
        star: "Star" = None,
    ):
        self.db = db
        self.check_interval = check_interval
        self.dynamic_check_interval = int(
            dynamic_check_interval or max(check_interval, 120)
        )
        self.live_check_interval = int(live_check_interval or check_interval)
        self.request_jitter_sec = max(0.0, float(request_jitter_sec))
        self.push_on_startup = push_on_startup
        self.on_new_post = on_new_post
        self.star = star

        self.bili_platform = BilibiliDynamic()
        self.live_platform = BilibiliLive()
        self.themes = self._build_themes()
        self.dispatcher = PostDispatcher(self.themes, self.on_new_post)
        self.dynamic_checker = DynamicSubscriptionChecker(
            self.bili_platform,
            self.dispatcher,
            star=self.star,
            request_delay_sec=request_delay_sec,
        )
        self.live_checker = LiveSubscriptionChecker(
            db=self.db,
            platform=self.live_platform,
            dispatcher=self.dispatcher,
            push_on_startup=self.push_on_startup,
            star=self.star,
            request_delay_sec=request_delay_sec,
            batch_size=live_batch_size,
        )

        self.running = False
        self.task: asyncio.Task | None = None
        self._next_dynamic_at = 0.0
        self._next_live_at = 0.0

    def _build_themes(self):
        renderer = HtmlRenderer(get_template_path())
        return {
            "dynamic_card": DynamicCardTheme(renderer),
            "movie_card": MovieCardTheme(renderer),
            "dynamic_movie_card": MovieCardTheme(
                renderer, template_name="dynamic_movie_card.html.jinja"
            ),
        }

    async def start(self):
        if self.running:
            return
        await BrowserManager.init()
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info(
            "Bilibili 调度器启动，"
            f"动态间隔 {self.dynamic_check_interval}s，直播间隔 {self.live_check_interval}s"
        )

    async def terminate(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await BrowserManager.close()
        logger.info("Bilibili 调度器已终止")

    async def _run_loop(self):
        self._next_dynamic_at = 0.0
        self._next_live_at = 0.0
        while self.running:
            await self._run_due_checks()
            await asyncio.sleep(self._sleep_duration())

    async def _run_due_checks(self):
        now = time.monotonic()
        if now >= self._next_dynamic_at:
            try:
                await self._check_dynamic()
            except Exception as exc:
                logger.error(f"动态调度错误: {exc}", exc_info=True)
            self._next_dynamic_at = self._next_due_at(self.dynamic_check_interval)

        now = time.monotonic()
        if now >= self._next_live_at:
            try:
                await self._check_live()
            except Exception as exc:
                logger.error(f"直播调度错误: {exc}", exc_info=True)
            self._next_live_at = self._next_due_at(self.live_check_interval)

    async def _check_all(self):
        await self._check_dynamic()
        await self._check_live()

    async def _check_dynamic(self):
        subs = self.db.get_enabled_subscriptions()
        dyn_subs = [sub for sub in subs if sub.sub_type == "dynamic"]
        if dyn_subs:
            await self.dynamic_checker.check(dyn_subs)

    async def _check_live(self):
        subs = self.db.get_enabled_subscriptions()
        live_subs = [sub for sub in subs if sub.sub_type == "live"]
        if live_subs:
            await self.live_checker.check(live_subs)

    async def manual_live_check(self, target_id: str) -> int:
        return await self.live_checker.manual_check(target_id)

    async def manual_live_check_all(self) -> tuple[int, int]:
        return await self.live_checker.manual_check_all()

    def _next_due_at(self, interval: int) -> float:
        jitter = random.uniform(0, self.request_jitter_sec)
        return time.monotonic() + max(1, int(interval)) + jitter

    def _sleep_duration(self) -> float:
        next_at = min(self._next_dynamic_at, self._next_live_at)
        if next_at <= 0:
            return 1.0
        return max(1.0, min(30.0, next_at - time.monotonic()))

    def _group_subs(self, subs: list[Subscription]):
        return group_subscriptions(subs)

    async def _dispatch_posts(self, platform_name, posts, user_infos):
        await self.dispatcher.dispatch(platform_name, posts, user_infos)
