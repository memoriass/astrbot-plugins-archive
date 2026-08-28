from __future__ import annotations

from dataclasses import asdict, dataclass
from time import time
from typing import Any
import uuid


DELIVERY_CONTEXT_VERSION = "plana.delivery.v1"


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    conversation_id: str
    turn_id: str
    source_message_id: str
    reply_to_message_id: str
    scope_id: str
    actor_id: str
    task_id: str = ""
    actor_display_name: str = ""
    resource_refs: tuple[str, ...] = ()
    delivery_mode: str = "reply"
    artifact_recipients: tuple[str, ...] = ()
    delivery_policy: str = "reply_then_mention"
    fallback_mode: str = "mention_same_scope"
    created_at: int = 0
    version: str = DELIVERY_CONTEXT_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifact_recipients"] = list(self.artifact_recipients)
        data["resource_refs"] = list(self.resource_refs)
        return data


def delivery_context_from_event(
    event: Any,
    *,
    scope_id: str,
    actor_id: str,
) -> DeliveryContext:
    message_obj = getattr(event, "message_obj", None)
    source_message_id = str(getattr(message_obj, "message_id", "") or "").strip()
    return DeliveryContext(
        conversation_id=str(getattr(event, "unified_msg_origin", "") or scope_id),
        turn_id=uuid.uuid4().hex,
        source_message_id=source_message_id,
        reply_to_message_id=source_message_id,
        scope_id=scope_id or "global",
        actor_id=actor_id or "user",
        actor_display_name=_sender_name(event),
        artifact_recipients=(actor_id or "user",),
        created_at=int(time()),
    )


def normalize_delivery_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    version = str(value.get("version") or DELIVERY_CONTEXT_VERSION).strip()
    if version != DELIVERY_CONTEXT_VERSION:
        return {}
    recipients = value.get("artifact_recipients")
    if not isinstance(recipients, (list, tuple)):
        recipients = []
    resource_refs = value.get("resource_refs")
    if not isinstance(resource_refs, (list, tuple)):
        resource_refs = []
    return {
        "version": DELIVERY_CONTEXT_VERSION,
        "conversation_id": str(value.get("conversation_id") or "")[:300],
        "turn_id": str(value.get("turn_id") or "")[:64],
        "source_message_id": str(value.get("source_message_id") or "")[:200],
        "reply_to_message_id": str(value.get("reply_to_message_id") or "")[:200],
        "scope_id": str(value.get("scope_id") or "global")[:200],
        "actor_id": str(value.get("actor_id") or "user")[:200],
        "task_id": str(value.get("task_id") or "")[:200],
        "actor_display_name": str(value.get("actor_display_name") or "")[:120],
        "delivery_mode": _choice(value.get("delivery_mode"), {"reply", "mention", "group", "private"}, "reply"),
        "resource_refs": [str(item)[:240] for item in resource_refs[:16] if str(item).strip()],
        "artifact_recipients": [str(item)[:200] for item in recipients[:8] if str(item).strip()],
        "delivery_policy": _choice(value.get("delivery_policy"), {"reply_then_mention", "private_only", "group", "retain_undelivered"}, "reply_then_mention"),
        "fallback_mode": _choice(value.get("fallback_mode"), {"mention_same_scope", "group", "undelivered"}, "mention_same_scope"),
        "created_at": _integer(value.get("created_at")),
    }


def remote_result_identity_error(
    run: dict[str, Any] | None,
    *,
    scope_id: str,
    actor_id: str,
) -> str:
    if not run:
        return ""
    stored_scope = str(run.get("scope_id") or "")
    stored_actor = str(run.get("actor_id") or "")
    if stored_scope and scope_id and stored_scope != scope_id:
        return "remote_result_scope_mismatch"
    if stored_actor and actor_id and stored_actor != actor_id:
        return "remote_result_actor_mismatch"
    return ""


def reply_message_id_from_event(event: Any) -> str:
    getter = getattr(event, "get_messages", None)
    if not callable(getter):
        return ""
    try:
        messages = getter()
    except Exception:  # noqa: BLE001
        return ""
    for component in messages or ():
        if component.__class__.__name__.lower() != "reply":
            continue
        reply_id = str(getattr(component, "id", "") or "").strip()
        if reply_id:
            return reply_id[:200]
    return ""


def run_matches_reply(run: dict[str, Any], reply_message_id: str) -> bool:
    if not reply_message_id:
        return False
    delivery = run.get("delivery_context")
    if not isinstance(delivery, dict):
        return False
    return reply_message_id in {
        str(delivery.get("source_message_id") or ""),
        str(delivery.get("reply_to_message_id") or ""),
    }


def _sender_name(event: Any) -> str:
    getter = getattr(event, "get_sender_name", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "")[:120]
    except Exception:  # noqa: BLE001
        return ""


def _choice(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
