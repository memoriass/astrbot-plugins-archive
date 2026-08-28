from __future__ import annotations

import importlib
from typing import Any


ENTRY_FILTER_MODULES = (
    "data.plugins.astrbot_plugin_plana_core.dialogue.entry_filters",
    "astrbot_plugin_plana_core.dialogue.entry_filters",
)


class CoreInProcessAdapter:
    """Calls Plana Core directly when Core and Bridge share one AstrBot process."""

    def _plugin(self) -> Any:
        for module_name in ENTRY_FILTER_MODULES:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError:
                continue
            getter = getattr(module, "get_active_plugin", None)
            if not callable(getter):
                continue
            plugin = getter()
            if plugin is not None and not bool(getattr(plugin, "_terminating", False)):
                return plugin
        return None

    def available(self) -> bool:
        return self._plugin() is not None

    def status(self) -> dict[str, Any]:
        plugin = self._plugin()
        if plugin is None:
            return {
                "ok": False,
                "transport": "in_process",
                "available": False,
                "error": "plana_core_not_active",
            }
        runtime = getattr(plugin, "runtime", None)
        contract = getattr(runtime, "bridge_contract", None)
        status = contract.status() if contract is not None else {}
        if not isinstance(status, dict):
            status = {}
        status.update(
            {
                "ok": True,
                "transport": "in_process",
                "available": True,
                "direct_runtime_dependency": True,
            }
        )
        return status

    async def payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        plugin = self._plugin()
        if plugin is None:
            return None
        runtime = getattr(plugin, "runtime", None)
        contract = getattr(runtime, "bridge_contract", None)
        handler = getattr(plugin, "_handle_bridge_payload", None)
        if contract is None or not callable(handler):
            return None
        normalized = contract.normalize_payload(payload)
        result = await handler(normalized)
        report = contract.result_report(normalized, result)
        report["transport"] = "in_process"
        return report

    def poll_proactive(self, limit: int) -> list[dict[str, Any]] | None:
        plugin = self._plugin()
        if plugin is None:
            return None
        queue = getattr(getattr(plugin, "runtime", None), "proactive_queue", None)
        poll = getattr(queue, "poll_ready", None)
        if not callable(poll):
            return None
        return poll(limit=max(1, min(int(limit or 5), 20)))

    def mark_proactive_delivered(
        self,
        task_id: int,
        request_id: str = "",
        *,
        runner_run_id: str = "",
        result_finalized: bool = False,
    ) -> bool | None:
        plugin = self._plugin()
        if plugin is None:
            return None
        queue = getattr(getattr(plugin, "runtime", None), "proactive_queue", None)
        mark = getattr(queue, "mark_delivered", None)
        if not callable(mark):
            return None
        ok = bool(mark(int(task_id), runner_run_id=runner_run_id))
        if ok and request_id and not result_finalized:
            store = getattr(getattr(plugin, "runtime", None), "remote_task_runs", None)
            submit = getattr(store, "mark_submitted", None)
            if callable(submit):
                submit(request_id, runner_run_id=runner_run_id)
        return ok

    def mark_proactive_failed(
        self,
        task_id: int,
        error: str,
        request_id: str = "",
        *,
        runner_run_id: str = "",
    ) -> bool | None:
        plugin = self._plugin()
        if plugin is None:
            return None
        queue = getattr(getattr(plugin, "runtime", None), "proactive_queue", None)
        mark = getattr(queue, "mark_failed", None)
        if not callable(mark):
            return None
        ok = bool(mark(int(task_id), error, runner_run_id=runner_run_id))
        if ok and request_id:
            store = getattr(getattr(plugin, "runtime", None), "remote_task_runs", None)
            update = getattr(store, "update", None)
            if callable(update):
                update(
                    request_id,
                    status="queued",
                    runner_run_id=runner_run_id,
                    error=error,
                )
        return ok
