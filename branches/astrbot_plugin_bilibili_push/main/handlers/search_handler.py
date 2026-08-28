from pathlib import Path

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..rendering import RendererPort
from ..workflows import render_workflow_result, run_bili_workflow
from ..workflows.models import WorkflowRequest


class SearchHandler:
    def __init__(self, context: Context, bg_dir: Path, renderer: RendererPort):
        self.bg_dir = bg_dir
        self.context = context
        self.renderer = renderer

    async def handle_search(self, event: AstrMessageEvent, keyword: str, star_inst):
        request = WorkflowRequest(
            "search_up",
            target=keyword,
            params={"query": keyword},
            source="command",
        )
        result = await run_bili_workflow(star_inst, event, request)
        yield await render_workflow_result(event, self.renderer, result)
