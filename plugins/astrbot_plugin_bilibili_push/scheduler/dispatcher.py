from collections.abc import Awaitable, Callable

from ..core.types import MessageSegment
from ..utils.logger import logger


class PostDispatcher:
    def __init__(
        self,
        themes: dict,
        on_new_post: Callable[[str, str, list[MessageSegment]], Awaitable[None]]
        | None,
    ):
        self.themes = themes
        self.on_new_post = on_new_post

    async def dispatch(self, platform_name, posts, user_infos):
        for user_info in user_infos:
            target_id = user_info.user_id
            for post in posts:
                if not self._category_matches(post, user_info):
                    continue
                await self._render_and_send(platform_name, target_id, post)

    def _category_matches(self, post, user_info) -> bool:
        if post.category in user_info.categories:
            return True
        if post.platform == "bilibili-live":
            logger.info(
                f"  [DISCARD] 直播分类不匹配: Post.cat={post.category} not in UserInfo.cats={user_info.categories}"
            )
        return False

    async def _render_and_send(self, platform_name, target_id, post):
        try:
            logger.info(
                f"  正在处理推送给 {target_id} | Platform: {post.platform} | Category: {post.category}"
            )
            theme = (
                self.themes["movie_card"]
                if post.platform == "bilibili-live"
                else self.themes["dynamic_movie_card"]
            )
            if not await theme.is_support_render(post):
                logger.warning(f"  主题 {type(theme).__name__} 不支持渲染该推文，跳过")
                return

            if not self.on_new_post:
                logger.warning("  未配置推送回调 (on_new_post is None)，消息已丢弃")
                return

            logger.info(
                f"  使用主题 {type(theme).__name__} 开始渲染并调用推送回调..."
            )
            msgs = await theme.render(post)
            await self.on_new_post(platform_name, target_id, msgs)
            logger.info("  回调调用完成")
        except Exception as exc:
            logger.error(f"推送失败: {exc}")
