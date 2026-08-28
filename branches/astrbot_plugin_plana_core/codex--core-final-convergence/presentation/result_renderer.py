from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from typing import Any

import aiohttp
from astrbot.api import logger

RENDER_URL = "http://127.0.0.1:6190/v1/render"
MAX_IMAGE_BYTES = 20 * 1024 * 1024


async def render_dialogue_result(context: Any, event: Any, document: dict[str, Any], fallback: str) -> Any:
    try:
        path = await render_document_to_file(document)
        return event.make_result().file_image(path)
    except Exception as exc:
        logger.warning("Plana result renderer failed, fallback to text: %s", exc)
        return event.plain_result(fallback)


async def render_document_to_file(document: dict[str, Any]) -> str:
    timeout = aiohttp.ClientTimeout(total=10, connect=2)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(RENDER_URL, json={"document": document}) as response:
            if response.status != 200:
                raise RuntimeError(f"renderer_http_{response.status}")
            image = await response.read()
            if not image.startswith(b"\x89PNG") or len(image) > MAX_IMAGE_BYTES:
                raise RuntimeError("renderer_response_invalid")
    output_dir = Path(tempfile.gettempdir()) / "astrbot_plugin_plana_core" / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image).hexdigest()
    path = output_dir / f"{digest}.png"
    if not path.exists():
        path.write_bytes(image)
    return str(path)


async def _render_to_file(document: dict[str, Any]) -> str:
    return await render_document_to_file(document)
