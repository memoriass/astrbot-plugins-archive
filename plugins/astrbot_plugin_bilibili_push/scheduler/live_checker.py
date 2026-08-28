import asyncio
import time

from ..core.compat import model_dump, type_validate_python
from ..database.db_manager import Subscription
from ..utils.logger import logger
from .subscription_group import group_subscriptions


STATUS_SUMMARY_LOG_INTERVAL_SEC = 3600


class LiveSubscriptionChecker:
    def __init__(
        self,
        db,
        platform,
        dispatcher,
        push_on_startup=False,
        star=None,
        request_delay_sec: float = 1.5,
        batch_size: int = 50,
    ):
        self.db = db
        self.platform = platform
        self.dispatcher = dispatcher
        self.push_on_startup = push_on_startup
        self.star = star
        self.request_delay_sec = max(0.0, float(request_delay_sec))
        self.batch_size = max(1, int(batch_size))
        self.status_cache: dict[str, object] = {}
        self.cache_loaded = False
        self.is_first_check = True
        self._summary_started_at = time.monotonic()
        self._last_summary_log_at = self._summary_started_at
        self._summary_rounds = 0
        self._summary_requested = 0
        self._summary_checked = 0
        self._summary_changed = 0
        self._summary_posts = 0
        self._summary_last_round_uids = 0
        self._summary_max_round_uids = 0

    async def check(self, subs: list[Subscription]):
        await self._load_status_cache(subs)
        current_is_first = self.is_first_check
        sub_units = group_subscriptions(subs)
        batches = list(self._chunks(sub_units))
        round_requested = len(sub_units)
        round_checked = 0
        round_changed = 0
        round_posts = 0

        for index, batch in enumerate(batches):
            pairs = await self._fetch_status_pairs(batch)
            round_checked += len(pairs)
            for sub_unit, new_status in pairs:
                post_count = await self._handle_status(
                    sub_unit,
                    new_status,
                    current_is_first,
                )
                if post_count:
                    round_changed += 1
                    round_posts += post_count
            if index < len(batches) - 1:
                await self._pause_between_requests()

        self.is_first_check = False
        self._record_periodic_summary(
            requested=round_requested,
            checked=round_checked,
            changed=round_changed,
            posts=round_posts,
        )

    async def manual_check(self, target_id: str) -> int:
        subs = self.db.get_enabled_subscriptions(target_id)
        live_subs = [sub for sub in subs if sub.sub_type == "live"]
        live_uids = len(group_subscriptions(live_subs))
        logger.info(f"手动直播检查开始 | Target: {target_id} | LiveUIDs: {live_uids}")
        pushed = await self._manual_check_subs(live_subs)
        logger.info(
            f"手动直播检查完成 | Target: {target_id} | LiveUIDs: {live_uids} | Pushed: {pushed}"
        )
        return pushed

    async def manual_check_all(self) -> tuple[int, int]:
        live_subs = [
            sub
            for sub in self.db.get_enabled_subscriptions()
            if sub.sub_type == "live"
        ]
        targets = {sub.target_id for sub in live_subs}
        live_uids = len(group_subscriptions(live_subs))
        logger.info(
            f"全部直播检查开始 | Targets: {len(targets)} | LiveUIDs: {live_uids}"
        )
        pushed = await self._manual_check_subs(live_subs)
        logger.info(
            f"全部直播检查完成 | Targets: {len(targets)} | LiveUIDs: {live_uids} | Pushed: {pushed}"
        )
        return len(targets), pushed

    async def _load_status_cache(self, subs: list[Subscription]):
        if self.cache_loaded:
            return
        if self.star:
            try:
                for sub_unit in group_subscriptions(subs):
                    uid = sub_unit.sub_target
                    raw_data = await self.star.get_kv_data(f"live_status_{uid}", None)
                    if raw_data:
                        try:
                            self.status_cache[uid] = type_validate_python(
                                self.platform.Info, raw_data
                            )
                        except Exception as exc:
                            logger.warning(f"恢复直播状态缓存失败 {uid}: {exc}")
            except Exception as exc:
                logger.warning(f"加载直播状态缓存出错: {exc}")
        self.cache_loaded = True

    def _build_posts(self, uid: str, new_status, current_is_first: bool):
        old_status = self.status_cache.get(uid)
        posts = []

        if old_status:
            posts = self.platform.compare_status(uid, old_status, new_status)
        elif new_status.live_status == 1 and (
            not current_is_first or self.push_on_startup
        ):
            posts = [self.platform._gen_current_status(new_status, 1)]

        if posts:
            logger.info(
                f"直播状态更新 [UID:{uid}] - 准备分发推送消息 (状态: {new_status.live_status})"
            )
        return posts

    async def _handle_status(self, sub_unit, new_status, current_is_first: bool):
        uid = sub_unit.sub_target
        posts = self._build_posts(uid, new_status, current_is_first)
        if posts:
            parsed_posts = []
            for raw in posts:
                parsed_post = await self.platform.parse(raw)
                logger.info(f"  已解析直播 Post: {parsed_post.title}")
                parsed_posts.append(parsed_post)
            await self.dispatcher.dispatch(
                self.platform.platform_name,
                parsed_posts,
                sub_unit.user_sub_infos,
            )

        self.status_cache[uid] = new_status
        if self.star:
            await self.star.put_kv_data(f"live_status_{uid}", model_dump(new_status))
        return len(posts)

    async def _manual_check_subs(self, live_subs: list[Subscription]) -> int:
        count = 0
        sub_units = group_subscriptions(live_subs)
        batches = list(self._chunks(sub_units))
        for index, batch in enumerate(batches):
            for sub_unit, new_status in await self._fetch_status_pairs(batch):
                if new_status.live_status != 1:
                    continue
                raw_post = self.platform._gen_current_status(new_status, 1)
                parsed_post = await self.platform.parse(raw_post)
                await self.dispatcher.dispatch(
                    self.platform.platform_name,
                    [parsed_post],
                    sub_unit.user_sub_infos,
                )
                count += 1
            if index < len(batches) - 1:
                await self._pause_between_requests()
        return count

    async def _fetch_status_pairs(self, batch):
        targets = [sub_unit.sub_target for sub_unit in batch]
        try:
            statuses = await self.platform.batch_get_status(targets)
            if len(statuses) != len(batch):
                raise ValueError(
                    f"直播接口返回数量不匹配: targets={len(batch)}, statuses={len(statuses)}"
                )
            return list(zip(batch, statuses))
        except Exception as exc:
            if len(batch) <= 1 or self._is_risk_error(exc):
                uid = targets[0] if targets else "-"
                logger.error(f"直播检查失败 UID:{uid}: {exc}")
                return []

            midpoint = len(batch) // 2
            logger.warning(f"直播批量检查失败，拆分批次重试: {exc}")
            left = await self._fetch_status_pairs(batch[:midpoint])
            await self._pause_between_requests()
            right = await self._fetch_status_pairs(batch[midpoint:])
            return left + right

    def _chunks(self, items):
        for index in range(0, len(items), self.batch_size):
            yield items[index:index + self.batch_size]

    def _record_periodic_summary(
        self,
        *,
        requested: int,
        checked: int,
        changed: int,
        posts: int,
    ):
        if self._summary_rounds == 0:
            now = time.monotonic()
            self._summary_started_at = now
            self._last_summary_log_at = now
        self._summary_rounds += 1
        self._summary_requested += requested
        self._summary_checked += checked
        self._summary_changed += changed
        self._summary_posts += posts
        self._summary_last_round_uids = requested
        self._summary_max_round_uids = max(self._summary_max_round_uids, requested)
        self._maybe_log_periodic_summary()

    def _maybe_log_periodic_summary(self):
        now = time.monotonic()
        if now - self._last_summary_log_at < STATUS_SUMMARY_LOG_INTERVAL_SEC:
            return

        stable = max(0, self._summary_checked - self._summary_changed)
        failed = max(0, self._summary_requested - self._summary_checked)
        minutes = max(1, int((now - self._summary_started_at) / 60))
        logger.info(
            "直播状态检查统计 | "
            f"窗口: {minutes} 分钟 | "
            f"轮次: {self._summary_rounds} | "
            f"当前去重UID: {self._summary_last_round_uids} | "
            f"峰值去重UID: {self._summary_max_round_uids} | "
            f"累计查询: {self._summary_checked}/{self._summary_requested} | "
            f"无变化查询: {stable} | "
            f"变动UID次数: {self._summary_changed} | "
            f"推送事件: {self._summary_posts} | "
            f"查询失败: {failed}"
        )
        self._reset_periodic_summary(now)

    def _reset_periodic_summary(self, now: float):
        self._summary_started_at = now
        self._last_summary_log_at = now
        self._summary_rounds = 0
        self._summary_requested = 0
        self._summary_checked = 0
        self._summary_changed = 0
        self._summary_posts = 0
        self._summary_last_round_uids = 0
        self._summary_max_round_uids = 0

    async def _pause_between_requests(self):
        if self.request_delay_sec > 0:
            await asyncio.sleep(self.request_delay_sec)

    @staticmethod
    def _is_risk_error(exc: Exception) -> bool:
        text = str(exc)
        return any(code in text for code in ("352", "403", "412", "risk control"))
