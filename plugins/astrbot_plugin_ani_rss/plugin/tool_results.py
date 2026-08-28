from __future__ import annotations

from typing import Any

from .sqlite_store import RuntimeStorageMixin


class PluginToolResultMixin(RuntimeStorageMixin):
    def record_workflow_tool_result(
        self,
        *,
        origin: str,
        workflow: str,
        target: str,
        source: str,
        success: bool,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.runtime_store().record_tool_result(
            origin=origin,
            workflow=workflow,
            target=target,
            source=source,
            success=success,
            summary=summary,
            payload=payload,
        )
