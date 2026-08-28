from __future__ import annotations

import re
from typing import Any

from .models import COMPILED_WORKFLOWS, WorkflowRequest
from .utils import (
    _canonical_key,
    _normalize_season,
    _normalize_workflow,
    _parse_kv_words,
    _split_words,
)


def workflow_from_pending_shortcut(text: str) -> WorkflowRequest | None:
    """Build a continue request from short task commands like `ani1a2b3c4d 1`."""
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    match = re.fullmatch(
        r"(?i)ani([0-9a-f]{3,8})(?:\s+(.+))?",
        raw,
    )
    if not match:
        return None

    task_hex = str(match.group(1) or "").lower()
    action = str(match.group(2) or "").strip()
    if not task_hex or not action:
        return None

    task_ref = f"ani{task_hex}"
    params: dict[str, Any] = {}
    normalized_action = re.sub(r"\s+", "", action)
    choice_match = re.fullmatch(r"(?:选|选择)?(\d{1,2})", normalized_action)
    if choice_match:
        params["choice"] = choice_match.group(1)
    else:
        params["action"] = action

    return WorkflowRequest(
        workflow="continue_pending",
        target=task_ref,
        params=params,
        source="cli",
    )


def workflow_from_cli(sub: str, args: str = "") -> WorkflowRequest | None:
    """Build a workflow request from `anirss <workflow> [args...]` after AstrBot strips wake_prefix."""
    raw_workflow = _canonical_key(sub)
    workflow = _normalize_workflow(raw_workflow)
    if workflow not in COMPILED_WORKFLOWS:
        return None

    text = str(args or "").strip()
    parts = _split_words(text)
    params: dict[str, Any] = {}
    target = ""

    if workflow == "add_subscription":
        target = text
    elif workflow in {"add_mikan_subscription", "search_mikan"}:
        target = text
    elif workflow == "recommend_mikan_subscription":
        params = _parse_kv_words(text)
        words = [part for part in parts if "=" not in part]
        if len(words) >= 2 and words[0].isdigit() and _normalize_season(words[1]):
            params["year"] = words[0]
            params["season"] = words[1]
            target = " ".join(words[2:])
        else:
            target = " ".join(words)
    elif workflow == "preview_subscription":
        target = text
    elif workflow == "list_subscriptions":
        numeric_parts = [part for part in parts if part.isdigit()]
        params["limit"] = numeric_parts[0] if numeric_parts else "20"
        params["enabled_only"] = True
    elif workflow == "refresh_subscription":
        target = text
    elif workflow == "continue_pending":
        params = _parse_kv_words(text)
        words = [part for part in parts if "=" not in part]
        if raw_workflow in {"确认", "取消"}:
            target = words[0] if words else ""
            params["action"] = raw_workflow
        elif raw_workflow in {"选", "选择"}:
            if len(words) > 1 and re.fullmatch(r"\d{1,2}", words[0]):
                params["choice"] = words[0]
                target = words[1]
            else:
                target = words[0] if words else ""
                if len(words) > 1:
                    params["choice"] = " ".join(words[1:])
        else:
            target = words[0] if words else ""
            if len(words) > 1:
                params["choice"] = " ".join(words[1:])
    elif workflow in {"refresh_all", "check_status"}:
        target = ""

    return WorkflowRequest(workflow=workflow, target=target, params=params, source="cli")
