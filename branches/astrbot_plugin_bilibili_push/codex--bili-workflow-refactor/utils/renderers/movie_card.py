import datetime
from .base import Theme
from ...core.types import Post
import astrbot.api.message_components as Comp


class MovieCardTheme(Theme):
    def __init__(self, renderer, template_name="movie_card.html.jinja"):
        self.renderer = renderer
        self.template_name = template_name

    async def render(self, post: Post) -> list:
        dt = datetime.datetime.fromtimestamp(post.timestamp)
        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # 获取封面图
        cover = ""
        if post.images and len(post.images) > 0:
            cover = post.images[0]
        elif post.repost and post.repost.images and len(post.repost.images) > 0:
            cover = post.repost.images[0]

        img_bytes = await self.renderer.render(
            self.template_name,
            {"post": post, "date_str": date_str, "cover": cover},
            selector=".movie-card",
        )
        return [Comp.Image.fromBytes(img_bytes)]
