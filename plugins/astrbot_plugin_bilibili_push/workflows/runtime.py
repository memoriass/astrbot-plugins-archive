from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent


def event_origin(event: AstrMessageEvent) -> str:
    return str(
        getattr(event, "unified_msg_origin", "")
        or getattr(event, "session_id", "")
        or "",
    )


def event_message_text(event: AstrMessageEvent) -> str:
    getter = getattr(event, "get_message_str", None)
    if callable(getter):
        return str(getter() or "")
    return str(getattr(event, "message_str", "") or "")


def event_reply_texts(event: AstrMessageEvent) -> list[str]:
    messages = getattr(getattr(event, "message_obj", None), "message", None) or []
    texts = []
    for component in messages:
        if component.__class__.__name__ != "Reply":
            continue
        texts.extend(_reply_component_texts(component))
    return _unique_texts(texts)


def event_text_bundle(event: AstrMessageEvent) -> list[str]:
    return _unique_texts([event_message_text(event), *event_reply_texts(event)])


def _reply_component_texts(reply, depth: int = 0) -> list[str]:
    if depth > 4:
        return []

    texts = []
    for attr in ("chain", "message", "origin", "content"):
        texts.extend(_chain_texts(getattr(reply, attr, None), depth + 1))
    for attr in ("message_str", "text"):
        value = getattr(reply, attr, "") or ""
        if value:
            texts.append(str(value))
    return texts


def _chain_texts(payload, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    if isinstance(payload, str):
        return [payload]
    if not isinstance(payload, list):
        return []

    texts = []
    for component in payload:
        if component.__class__.__name__ == "Reply":
            texts.extend(_reply_component_texts(component, depth + 1))
            continue
        for attr in ("text", "message_str"):
            value = getattr(component, attr, "") or ""
            if value:
                texts.append(str(value))
        for attr in ("chain", "message", "origin", "content"):
            texts.extend(_chain_texts(getattr(component, attr, None), depth + 1))
    return texts


def _unique_texts(texts: list[str]) -> list[str]:
    seen = set()
    unique = []
    for text in texts:
        value = str(text or "")
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def message_event_from_tool_arg(event: Any) -> AstrMessageEvent:
    context = getattr(event, "context", None)
    actual_event = getattr(context, "event", None)
    return actual_event or event
