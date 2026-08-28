from __future__ import annotations

from pathlib import Path

from ..utils.html_renderer import HtmlRenderer
from .renderer_port import RendererPort


class HtmlRendererAdapter(RendererPort):
    def __init__(self, template_path: Path):
        self._renderer = HtmlRenderer(template_path)

    async def render(
        self,
        template_name: str,
        templates: dict,
        viewport: dict | None = None,
        selector: str = "body",
    ) -> bytes:
        return await self._renderer.render(
            template_name=template_name,
            templates=templates,
            viewport=viewport,
            selector=selector,
        )
