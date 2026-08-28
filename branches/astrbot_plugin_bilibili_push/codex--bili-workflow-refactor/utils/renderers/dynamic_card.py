import datetime
import markdown
from pathlib import Path
from .base import Theme
from ...core.types import Post
import astrbot.api.message_components as Comp


class DynamicCardTheme(Theme):
    def __init__(self, renderer, template_name="dynamic_card.html.jinja"):
        self.renderer = renderer
        self.template_name = template_name

    async def render(self, post: Post) -> list:
        dt = datetime.datetime.fromtimestamp(post.timestamp)
        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        md_lines = []
        if post.title:
            md_lines.append(f"## {post.title}")

        if post.repost:
            md_lines.append(f"> 转发 @{post.repost.nickname}:")
            if post.repost.title:
                md_lines.append(f"> **{post.repost.title}**")
            md_lines.append(f"> {post.repost.content}")
            for img in getattr(post.repost, "images", []):
                md_lines.append(f"> ![]({img})")
            md_lines.append("\n---")

        if post.content:
            md_lines.append(post.content)

        for img in getattr(post, "images", []):
            md_lines.append(f"![]({img})")

        html_content = markdown.markdown("\n\n".join(md_lines))

        img_bytes = await self.renderer.render(
            self.template_name, {"content_html": html_content}, selector="body"
        )
        return [Comp.Image.fromBytes(img_bytes)]
