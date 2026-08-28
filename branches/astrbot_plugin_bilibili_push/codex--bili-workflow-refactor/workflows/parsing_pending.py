from __future__ import annotations

from .models import WorkflowRequest
from .pending import task_ref_from_text
from .runtime import event_message_text, event_reply_texts


def workflow_from_pending_event(event) -> WorkflowRequest | None:
    text = event_message_text(event)
    task_ref = _task_ref_from_reply(event)
    if task_ref:
        return WorkflowRequest(
            workflow="continue_pending",
            target=task_ref,
            params={"task_id": task_ref, "action": text.strip()},
            source="pending",
        )
    return None


def _task_ref_from_reply(event) -> str:
    for text in event_reply_texts(event):
        task_ref = task_ref_from_text(text)
        if task_ref:
            return task_ref
    return ""
