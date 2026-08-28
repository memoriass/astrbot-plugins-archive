from __future__ import annotations

from .models import WorkflowRequest
from .utils import normalize_workflow, parse_params


def workflow_from_tool(
    workflow: str,
    target: str = "",
    params: object = "",
) -> WorkflowRequest:
    parsed = parse_params(params)
    selected = normalize_workflow(workflow or str(parsed.get("workflow") or ""))
    return WorkflowRequest(
        workflow=selected or "search_up",
        target=str(target or parsed.get("target") or ""),
        params=parsed,
        source="tool",
    )
