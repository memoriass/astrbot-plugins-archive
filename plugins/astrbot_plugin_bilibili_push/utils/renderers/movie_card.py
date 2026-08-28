from dataclasses import replace
from pathlib import Path

import astrbot.api.message_components as Comp

from .base import Theme
from ...core.types import Post
from ...utils.image_optimizer import (
    AVATAR_POLICY,
    DEFAULT_AVATAR_DATA_URI,
    DYNAMIC_HERO_POLICY,
    LIVE_COVER_POLICY,
    TRANSPARENT_IMAGE_DATA_URI,
    optimize_template_image,
)
from ...utils.timezone import format_bilibili_time


class MovieCardTheme(Theme):
    def __init__(
        self,
        renderer,
        template_name="movie_card.html.jinja",
        display_timezone="Asia/Shanghai",
        avatar_cache_dir: Path | None = None,
    ):
        self.renderer = renderer
        self.template_name = template_name
        self.display_timezone = display_timezone
        self.avatar_cache_dir = avatar_cache_dir

    async def render(self, post: Post) -> list:
        date_str = format_bilibili_time(
            post.timestamp,
            timezone_name=self.display_timezone,
        )

        cover = ""
        if post.images and len(post.images) > 0:
            cover = post.images[0]
        elif post.repost and post.repost.images and len(post.repost.images) > 0:
            cover = post.repost.images[0]

        template_post, cover = await self._prepare_template_images(post, cover)
        img_bytes = await self.renderer.render(
            self.template_name,
            {"post": template_post, "date_str": date_str, "cover": cover},
            selector=".movie-card",
        )
        return [Comp.Image.fromBytes(img_bytes)]

    async def _prepare_template_images(self, post: Post, cover):
        is_dynamic_template = self.template_name == "dynamic_movie_card.html.jinja"
        cover_policy = DYNAMIC_HERO_POLICY if is_dynamic_template else LIVE_COVER_POLICY
        original_cover = _original_cover(post)
        if cover:
            cover = await optimize_template_image(
                cover,
                cover_policy,
                label="cover",
                fallback=TRANSPARENT_IMAGE_DATA_URI,
            )
        return (
            await _clone_post_for_template(
                post,
                original_cover,
                cover,
                self.avatar_cache_dir,
            ),
            cover,
        )


def _original_cover(post: Post):
    if post.images and len(post.images) > 0:
        return post.images[0]
    if post.repost and post.repost.images and len(post.repost.images) > 0:
        return post.repost.images[0]
    return ""


async def _clone_post_for_template(
    post: Post | None,
    original_cover,
    optimized_cover,
    avatar_cache_dir: Path | None = None,
) -> Post | None:
    if post is None:
        return None
    avatar = await optimize_template_image(
        post.avatar,
        AVATAR_POLICY,
        label="avatar",
        fallback=DEFAULT_AVATAR_DATA_URI,
        cache_dir=avatar_cache_dir,
    )
    images = _replace_first_image(list(post.images or []), original_cover, optimized_cover)
    repost = await _clone_post_for_template(
        post.repost,
        original_cover,
        optimized_cover,
        avatar_cache_dir,
    )
    return replace(post, avatar=avatar, images=images, repost=repost)


def _replace_first_image(images: list, original_cover, optimized_cover) -> list:
    if not original_cover or not optimized_cover:
        return images
    for index, image in enumerate(images):
        if image == original_cover:
            images[index] = optimized_cover
            break
    return images
