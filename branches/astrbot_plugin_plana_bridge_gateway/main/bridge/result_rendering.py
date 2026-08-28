from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from typing import Any

import aiohttp
from astrbot.api import logger
from astrbot.api.event import MessageChain

RENDER_URL = "http://127.0.0.1:6190/v1/render"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


async def render_result_chain(context: Any, payload: dict[str, Any], fallback: str) -> MessageChain:
    try:
        document = _document_for(payload, fallback)
        path = await _render_to_file(document)
        chain = MessageChain().file_image(path)
        caption = str(document.get("summary") or "").strip()[:180]
        if caption:
            chain.message("\n" + caption)
        return chain
    except Exception as exc:
        logger.warning("Plana Bridge result renderer failed, fallback to text: %s", exc)
        return MessageChain().message(fallback)


async def _render_to_file(document: dict[str, Any]) -> str:
    timeout = aiohttp.ClientTimeout(total=12, connect=2)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(RENDER_URL, json={"document": document}) as response:
            if response.status != 200:
                raise RuntimeError(f"renderer_http_{response.status}")
            image = await response.read()
            if not image.startswith(b"\x89PNG") or len(image) > MAX_IMAGE_BYTES:
                raise RuntimeError("renderer_response_invalid")
    output_dir = Path(tempfile.gettempdir()) / "astrbot_plugin_plana_bridge_gateway" / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image).hexdigest()
    path = output_dir / f"{digest}.png"
    if not path.exists():
        path.write_bytes(image)
    return str(path)


def _document_for(payload: dict[str, Any], user_summary: str = "") -> dict[str, Any]:
    status = str(payload.get("status") or "info")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    subscriptions = result.get("subscriptions")
    if isinstance(subscriptions, list):
        return {
            "contract_version": "plana.render.v1",
            "template": "ani_rss",
            "title": "ANI-RSS Subscriptions",
            "status": status,
            "summary": user_summary or payload.get("result_summary") or result.get("result_summary") or "",
            "items": subscriptions,
            "metadata": {"count": result.get("count", len(subscriptions)), "read_only": result.get("read_only", True)},
        }
    return {
        "contract_version": "plana.render.v1",
        "template": "task_result",
        "title": "任务结果",
        "status": status,
        "summary": user_summary or payload.get("result_summary") or payload.get("summary") or payload.get("error") or "",
        "artifacts": payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
        "metadata": {"request_id": payload.get("request_id") or "", "runner_run_id": payload.get("runner_run_id") or payload.get("run_id") or ""},
    }
