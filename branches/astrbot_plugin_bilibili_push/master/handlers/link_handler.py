import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..parser.video_downloader import BilibiliVideoDownloader
from ..rendering import RendererPort


class LinkParserHandler:
    def __init__(
        self,
        context: Context,
        renderer: RendererPort,
        template_name: str = "parser_bili",
        video_downloader: BilibiliVideoDownloader | None = None,
        enable_video_download: bool = False,
    ):
        self.context = context
        self.template_name = template_name
        self.renderer = renderer
        self.video_downloader = video_downloader
        self.enable_video_download = enable_video_download

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
            segments = [Comp.Image.fromBytes(img_bytes)]
            video_path = await self._maybe_download_video(info)
            if video_path:
                segments.append(Comp.Video.fromFileSystem(str(video_path.absolute())))
            yield event.chain_result(segments)
        except Exception as e:
            logger.error(f"Link parse render failed: {e}")

    async def _maybe_download_video(self, info: dict):
        if not self.enable_video_download or not self.video_downloader:
            return None
        try:
            return await self.video_downloader.download_for_parse(info)
        except Exception as exc:
            logger.warning(f"Link parse video attachment skipped: {exc}")
            return None
