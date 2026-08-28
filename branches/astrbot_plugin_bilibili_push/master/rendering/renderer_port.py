from __future__ import annotations

from typing import Protocol


class RendererPort(Protocol):
    async def render(
        self,
        template_name: str,
        templates: dict,
        viewport: dict | None = None,
        selector: str = "body",
    ) -> bytes: ...
