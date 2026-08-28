from __future__ import annotations

import astrbot.api.message_components as Comp
from astrbot.api import logger

from .markers import encode_task_marker
from .results import WorkflowResult


async def render_workflow_result(event, renderer, result: WorkflowResult):
    text = result.display_text or result.text
    marker = encode_task_marker(result.task_id) if result.task_id else ""
    if marker:
        text = f"{text}{marker}"
    if not result.cards:
        return event.plain_result(text)

    segments = []
    failed = False
    for card in result.cards:
        try:
            img_bytes = await renderer.render(
                card.template_name,
                card.templates,
                viewport=card.viewport,
                selector=card.selector,
            )
            segments.append(Comp.Image.fromBytes(img_bytes))
        except Exception as exc:
            failed = True
            logger.error(f"Workflow card render failed: {exc}", exc_info=True)

    if failed and not segments:
        return event.plain_result(f"{text}\n\n卡片渲染失败，已返回文本结果。")
    if failed:
        segments.append(Comp.Plain("部分卡片渲染失败。"))
    return event.chain_result(segments)
