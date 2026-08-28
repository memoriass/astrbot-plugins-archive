from __future__ import annotations

from dataclasses import dataclass
import re
from time import time
from typing import Any


_GENERAL_CONTINUATION_RE = re.compile(
    r"^(?:\u90a3(?:\u4e48|\u5c31|\u518d|\u7ee7\u7eed|\u63a5\u7740|\u5148|\u8fd8|\u628a|\u521a\u624d)|"
    r"\u7136\u540e|\u6240\u4ee5|\u8fd8\u6709|\u53e6\u5916|"
    r"\u5bf9\u4e86|\u7ee7\u7eed|\u63a5\u7740|\u518d\u6765|\u521a\u624d|\u4e0a\u9762|\u524d\u9762|"
    r"\u4f60\u8bf4\u7684|\u8fd9\u4e2a|\u90a3\u4e2a|\u5c31\u6309|\u8fd8\u662f\u6309|\u987a\u4fbf)",
    re.IGNORECASE,
)
_TASK_RESPONSE_RE = re.compile(
    r"^(?:\u53ef\u4ee5|\u597d(?:\u7684)?|\u884c|\u6ca1\u95ee\u9898|\u786e\u8ba4|\u7ee7\u7eed|"
    r"\u5f00\u59cb|\u6267\u884c|\u53d6\u6d88|\u7b97\u4e86|\u4e0d\u8981\u4e86|\u505c(?:\u6b62|\u4e00\u4e0b)?|"
    r"\u6539\u6210|\u6362\u6210|\u4e0d\u662f|\u91cd\u6765|\u91cd\u505a)"
    r"(?:\u5427|\u5462|\u554a|\u5440)?(?:[\uff0c,.\u3002!\uff01?\uff1f\s]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GroupContinuationAssessment:
    should_continue: bool
    continuation_signal: bool
    reply_signal: bool
    recent_task_state: bool
    reason: str


def assess_group_continuation(
    event: Any,
    session_state: Any | None,
    *,
    anchor_resolution: Any | None = None,
    scope_id: str = "",
    actor_id: str = "",
    now: float | None = None,
    max_state_age_seconds: float = 180.0,
) -> GroupContinuationAssessment:
    current_time = time() if now is None else float(now)
    recent_task_state = _has_recent_task_state(
        session_state,
        scope_id=scope_id,
        actor_id=actor_id,
        now=current_time,
        max_age_seconds=max_state_age_seconds,
    )
    text = _message_text(event)
    general_continuation = bool(_GENERAL_CONTINUATION_RE.search(text))
    task_response = bool(_TASK_RESPONSE_RE.search(text))
    continuation_signal = general_continuation or (
        recent_task_state and task_response
    )
    reply_signal = _has_reply_component(event)
    anchored_reply = reply_signal and anchor_resolution is not None
    owner_anchor = anchored_reply and bool(
        getattr(anchor_resolution, "is_owner", False)
    )
    public_fork = anchored_reply and not owner_anchor
    reply_continuation = reply_signal and recent_task_state
    should_continue = continuation_signal or reply_continuation or anchored_reply
    if owner_anchor:
        reason = "anchored_owner_reply"
    elif public_fork:
        reason = "anchored_public_fork"
    elif reply_continuation:
        reason = "recent_task_reply_signal"
    elif continuation_signal:
        reason = "text_continuation_signal"
    elif reply_signal:
        reason = "unanchored_reply_without_recent_task"
    elif recent_task_state:
        reason = "recent_task_without_continuation_signal"
    else:
        reason = "no_group_continuation_signal"
    return GroupContinuationAssessment(
        should_continue=should_continue,
        continuation_signal=continuation_signal,
        reply_signal=reply_signal,
        recent_task_state=recent_task_state,
        reason=reason,
    )


def _has_recent_task_state(
    session_state: Any | None,
    *,
    scope_id: str,
    actor_id: str,
    now: float,
    max_age_seconds: float,
) -> bool:
    if session_state is None or not _has_task_context(session_state):
        return False
    stored_scope = str(getattr(session_state, "scope_id", "") or "")
    stored_actor = str(getattr(session_state, "actor_id", "") or "")
    if scope_id and stored_scope and stored_scope != scope_id:
        return False
    if actor_id and stored_actor and stored_actor != actor_id:
        return False
    try:
        updated_at = float(getattr(session_state, "updated_at", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    max_age = max(1.0, float(max_age_seconds or 180.0))
    return updated_at > 0.0 and updated_at >= now - max_age


def _has_task_context(session_state: Any) -> bool:
    scalar_fields = (
        "latest_pending_run_id",
        "latest_prompt",
        "latest_route",
        "latest_llm_tool_pending",
        "latest_remote_authorization_pending",
        "latest_remote_request_id",
        "current_goal",
    )
    collection_fields = (
        "focus_stack",
        "active_tasks",
        "pending_disambiguation",
    )
    return any(bool(getattr(session_state, name, None)) for name in scalar_fields) or any(
        bool(getattr(session_state, name, None)) for name in collection_fields
    )


def _has_reply_component(event: Any) -> bool:
    getter = getattr(event, "get_messages", None)
    if not callable(getter):
        return False
    try:
        messages = getter()
    except Exception:  # noqa: BLE001
        return False
    return any(
        component.__class__.__name__.casefold() == "reply"
        for component in messages or ()
    )


def _message_text(event: Any) -> str:
    try:
        return " ".join(str(event.get_message_str() or "").strip().split())
    except Exception:  # noqa: BLE001
        return ""
