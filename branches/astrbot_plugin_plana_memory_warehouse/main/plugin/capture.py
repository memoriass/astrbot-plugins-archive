from __future__ import annotations

import hashlib
import time
from typing import Any

from .store_common import CONTRACT_VERSION


def build_event_payload(
    event: Any,
    *,
    role: str,
    event_type: str,
    min_content_chars: int,
    capture_commands: bool,
    excluded_prefixes: tuple[str, ...],
    content_override: str = "",
) -> dict[str, Any] | None:
    content = content_override if content_override else _event_text(event)
    if not _should_capture_text(
        content,
        min_content_chars=min_content_chars,
        capture_commands=capture_commands,
        excluded_prefixes=excluded_prefixes,
    ):
        return None
    platform = _safe_call(event, "get_platform_name")
    message_type = _message_type(event)
    session_id = _safe_call(event, "get_session_id")
    group_id = _safe_call(event, "get_group_id")
    actor_id = _global_actor_id(platform, _safe_call(event, "get_sender_id"))
    actor_name = _safe_call(event, "get_sender_name")
    origin = str(getattr(event, "unified_msg_origin", "") or "")
    message_id = _message_id(event)
    external_event_id = _external_event_id(
        platform,
        origin,
        message_id,
        role=role,
        event_type=event_type,
        content=content,
    )
    metadata = {
        "source": "astrbot_event_capture",
        "message_id": message_id,
        "is_private": _is_private(event),
    }
    if role == "assistant":
        metadata["assistant_actor"] = "plana"
    return {
        "contract_version": CONTRACT_VERSION,
        "scope_id": origin or session_id,
        "unified_msg_origin": origin,
        "platform": platform,
        "message_type": message_type,
        "session_id": session_id,
        "group_id": group_id,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "role": role,
        "event_type": event_type,
        "external_event_id": external_event_id,
        "content": content,
        "created_at": int(time.time()),
        "metadata": metadata,
    }


def _should_capture_text(
    text: str,
    *,
    min_content_chars: int,
    capture_commands: bool,
    excluded_prefixes: tuple[str, ...],
) -> bool:
    clean = str(text or "").strip()
    if len(clean) < min_content_chars:
        return False
    if not capture_commands and clean.startswith("/"):
        return False
    return not any(clean.startswith(prefix) for prefix in excluded_prefixes)


def _external_event_id(
    platform: str,
    origin: str,
    message_id: str,
    *,
    role: str,
    event_type: str,
    content: str,
) -> str:
    if not message_id:
        return ""
    suffix = event_type
    if role == "assistant":
        suffix = f"{suffix}:{_short_hash(content)}"
    return f"{platform}:{origin}:{message_id}:{suffix}"


def _safe_call(event: Any, method_name: str) -> str:
    method = getattr(event, method_name, None)
    if not callable(method):
        return ""
    try:
        value = method()
    except Exception:  # noqa: BLE001
        return ""
    return "" if value is None else str(value)


def _global_actor_id(platform: str, sender_id: str) -> str:
    clean_sender = str(sender_id or "").strip()
    if not clean_sender:
        return ""
    clean_platform = str(platform or "").strip()
    if not clean_platform:
        return clean_sender
    return f"{clean_platform}:{clean_sender}"


def _event_text(event: Any) -> str:
    method = getattr(event, "get_message_str", None)
    if callable(method):
        try:
            return str(method() or "")
        except Exception:  # noqa: BLE001
            return ""
    return str(getattr(event, "message_str", "") or "")


def _message_type(event: Any) -> str:
    value = _safe_call_raw(event, "get_message_type")
    return str(getattr(value, "value", value) or "")


def _is_private(event: Any) -> bool:
    method = getattr(event, "is_private_chat", None)
    if callable(method):
        try:
            return bool(method())
        except Exception:  # noqa: BLE001
            return False
    return False


def _message_id(event: Any) -> str:
    for path in (
        ("message_id",),
        ("message_obj", "message_id"),
        ("message_obj", "raw_message", "message_id"),
        ("message_obj", "raw_message", "message", "message_id"),
        ("message_obj", "raw_message", "message", "id"),
    ):
        value = _nested_attr(event, path)
        if value not in {None, ""}:
            return str(value)[:160]
    return ""


def _nested_attr(obj: Any, path: tuple[str, ...]) -> Any:
    value = obj
    for name in path:
        value = getattr(value, name, None)
        if value is None:
            return None
    return value


def _safe_call_raw(event: Any, method_name: str) -> Any:
    method = getattr(event, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:  # noqa: BLE001
        return None


def _short_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:12]
