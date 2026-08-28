from __future__ import annotations

from typing import Any

from .models import WorkflowRequest


def build_write_proposal(request: WorkflowRequest) -> dict[str, Any]:
    target_type = "series_id" if request.workflow == "refresh_series_metadata" else "library_id"
    target = str(request.params.get(target_type) or request.target or "").strip()
    arguments = {target_type: target} if target else {}
    return {
        "ok": True,
        "executed": False,
        "action": "write_pending",
        "operation": request.workflow,
        "arguments": arguments,
        "requires_confirmation": True,
        "message": "Komga 写操作仅生成待确认提案，插件不会直接执行。",
    }

