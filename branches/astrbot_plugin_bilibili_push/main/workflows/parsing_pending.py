from __future__ import annotations

import re

from .models import WorkflowRequest
from .pending import (
    looks_like_pending_action,
    looks_like_standalone_pending_action,
    task_ref_from_text,
)
from .runtime import event_message_text, event_reply_texts


def workflow_from_pending_event(event) -> WorkflowRequest | None:
    raw_text = event_message_text(event)
    text = _pending_action_text(event, raw_text)
    task_ref = _task_ref_from_reply(event)
    if task_ref:
        return WorkflowRequest(
            workflow="continue_pending",
            target=task_ref,
            params={"task_id": task_ref, "action": text.strip(), "via_reply": True},
            source="pending",
        )
    if event_reply_texts(event) and looks_like_pending_action(text):
        return WorkflowRequest(
            workflow="continue_pending",
            target="",
            params={"action": text.strip(), "via_reply": True},
            source="pending",
        )
    if getattr(event, "is_wake", False) and looks_like_standalone_pending_action(text):
        return WorkflowRequest(
            workflow="continue_pending",
            target="",
            params={"action": text.strip(), "via_reply": False},
            source="pending",
        )
    return None


def _task_ref_from_reply(event) -> str:
    for text in event_reply_texts(event):
        task_ref = task_ref_from_text(text)
        if task_ref:
            return task_ref
    return ""


def _pending_action_text(event, text: str) -> str:
    value = str(text or "").strip()
    if not getattr(event, "is_wake", False):
        return value
    stripped = _strip_leading_wake_word(value)
    if stripped and (
        looks_like_pending_action(stripped)
        or looks_like_standalone_pending_action(stripped)
    ):
        return stripped
    return value


def _strip_leading_wake_word(text: str) -> str:
    return re.sub(r"^[A-Za-z0-9_\-]{1,24}\s+", "", text, count=1).strip()
