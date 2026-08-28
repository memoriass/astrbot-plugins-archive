from __future__ import annotations

import json
import shlex
from typing import Any

from .models import COMPILED_WORKFLOWS, WorkflowRequest


def workflow_from_tool(
    workflow: str,
    target: str = "",
    params: object = "",
) -> WorkflowRequest:
    payload = _params(params)
    selected = _normalize(workflow)
    if selected not in COMPILED_WORKFLOWS:
        payload.setdefault("text", " ".join(part for part in (workflow, target) if part))
        selected = "ai_dispatch"
    return WorkflowRequest(selected, str(target or "").strip(), payload, "tool")


def workflow_from_cli(workflow: str, args: str = "") -> WorkflowRequest | None:
    selected = _normalize(workflow)
    if selected not in COMPILED_WORKFLOWS:
        return None
    words = shlex.split(str(args or ""))
    payload: dict[str, Any] = {}
    target_words: list[str] = []
    for word in words:
        if "=" not in word:
            target_words.append(word)
            continue
        key, value = word.split("=", 1)
        payload[key.strip()] = value.strip()
    target = " ".join(target_words).strip()
    return WorkflowRequest(selected, target, payload, "cli")


def _params(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}
    return dict(parsed) if isinstance(parsed, dict) else {"value": parsed}


def _normalize(value: str) -> str:
    return str(value or "").strip().casefold().replace("komga.", "").replace("-", "_")

