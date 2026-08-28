import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..rendering import RendererPort


class LinkParserHandler:
    def __init__(
        self,
        context: Context,
        renderer: RendererPort,
        template_name: str = "parser_bili",
    ):
        self.context = context
        self.template_name = template_name
        self.renderer = renderer

    async def handle_links(self, event: AstrMessageEvent, parser, enable_link_parser):
        if not enable_link_parser:
            return
        info = await parser.parse_message(event.message_str)
        if not info:
            return
        try:
            final_template = (
                f"{self.template_name}.html.jinja"
                if not self.template_name.endswith(".jinja")
                else self.template_name
            )
            img_bytes = await self.renderer.render(
                final_template,
                info,
                viewport={"width": 640, "height": 800},
                selector=".card",
            )
            yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
        except Exception as e:
            logger.error(f"Link parse render failed: {e}")
