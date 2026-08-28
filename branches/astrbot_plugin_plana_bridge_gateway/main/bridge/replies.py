from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain


async def send_reply(event: AstrMessageEvent, reply: dict[str, Any]) -> None:
    chain = reply_to_chain(reply)
    if chain:
        await event.send(chain)


def reply_to_chain(reply: dict[str, Any]) -> MessageChain | None:
    reply_type = str(reply.get("type", "text"))
    chain = MessageChain()
    if reply_type == "text":
        text = str(reply.get("text", ""))
        return chain.message(text) if text else None
    if reply_type == "image_url":
        return chain.url_image(str(reply.get("url", "")))
    if reply_type == "image_file":
        return chain.file_image(str(reply.get("path", "")))
    if reply_type == "image_base64":
        return chain.base64_image(str(reply.get("base64", "")))
    logger.warning("Plana Bridge Gateway unsupported reply type: %s", reply_type)
    return None
