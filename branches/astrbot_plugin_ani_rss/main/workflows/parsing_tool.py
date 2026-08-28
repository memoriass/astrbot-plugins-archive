from __future__ import annotations

from typing import Any

from .models import COMPILED_WORKFLOWS, WorkflowRequest
from .utils import _first_text, _normalize_workflow, _parse_params


def workflow_from_tool(
    workflow: str,
    target: str = "",
    params: str | dict[str, Any] | None = "",
) -> WorkflowRequest:
    """Build a workflow request from the LLM tool shape."""
    payload = _parse_params(params)
    selected = _normalize_workflow(workflow or str(payload.get("workflow") or ""))
    if selected not in COMPILED_WORKFLOWS:
        fallback_text = _first_text(
            {"workflow": workflow, "target": target, **payload},
            "text",
            "message",
            "prompt",
            "query",
            "title",
            "name",
            "target",
            "_raw",
            "workflow",
        )
        if fallback_text:
            selected = "ai_dispatch"
            payload.setdefault("text", fallback_text)
    resolved_target = _first_text(
        {"target": target, **payload},
        "target",
        "rss_url",
        "url",
        "query",
        "title",
        "task_id",
        "subscription_id",
        "id",
    )
    return WorkflowRequest(
        workflow=selected,
        target=resolved_target,
        params=payload,
        source="tool",
    )
