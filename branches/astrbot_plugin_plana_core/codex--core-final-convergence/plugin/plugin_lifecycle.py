from __future__ import annotations

import asyncio
from time import time

from astrbot.api import logger

from ..dialogue.entry_filters import get_active_plugin, set_active_plugin
from ..utils.time_utils import is_quiet_time


class PlanaPluginLifecycleMixin:
    async def terminate(self) -> None:
        """插件卸载或重载时优雅停止所有后台任务。"""
        self._terminating = True
        gallery_context = getattr(self, "_gallery_context", None)
        if gallery_context is not None:
            gallery_context.release_all()
        dialogue = getattr(self, "dialogue", None)
        if dialogue is not None and hasattr(dialogue, "stop"):
            await dialogue.stop()
        passive_tasks = list(getattr(self, "_passive_observe_tasks", set()))
        for task in passive_tasks:
            if not task.done():
                task.cancel()
        if passive_tasks:
            await asyncio.gather(*passive_tasks, return_exceptions=True)
            getattr(self, "_passive_observe_tasks", set()).clear()
        progress_tasks = list(getattr(self, "_tool_progress_tasks", {}).values())
        for task in progress_tasks:
            if not task.done():
                task.cancel()
        if progress_tasks:
            await asyncio.gather(*progress_tasks, return_exceptions=True)
            getattr(self, "_tool_progress_tasks", {}).clear()
        await self.runtime.job_manager.stop_all()
        if self.runtime.enable_recall_tool:
            self._remove_llm_tool("plana_recall_memory")
        self._remove_llm_tool("web_search_searxng")
        if get_active_plugin() is self:
            set_active_plugin(None)
        logger.info("Plana core terminated.")

    def _remove_llm_tool(self, name: str) -> None:
        try:
            manager = self.context.get_llm_tool_manager()
            manager.remove_func(name)
        except Exception:  # noqa: BLE001
            logger.debug("Plana LLM tool unregister skipped: %s", name, exc_info=True)

    async def _maintenance_cycle(self) -> None:
        await self._run_quiet_hours_gate()
        await self._run_memory_maintenance()
        await self._run_concept_accumulation()
        self.runtime.decay_state()
        await self._run_proactive_delivery()
        cleaned = self.runtime.proactive_queue.cleanup_old(max_age_days=30)
        if cleaned:
            logger.debug("Plana maintenance: proactive cleanup=%d", cleaned)
        logger.debug("Plana maintenance cycle completed")

    async def _run_quiet_hours_gate(self) -> None:
        if not self.quiet_hours:
            return
        in_quiet = is_quiet_time(self.quiet_hours)
        if in_quiet and not self._quiet_hours_active:
            self._quiet_hours_active = True
            if self.runtime.mode != "silent":
                self.runtime.set_mode("silent")
                logger.info(
                    "Plana quiet_hours started (%s): switched to silent",
                    self.quiet_hours,
                )
        elif not in_quiet and self._quiet_hours_active:
            self._quiet_hours_active = False
            if self.runtime.mode == "silent":
                restore_mode = getattr(self.runtime, "configured_mode", "standby")
                self.runtime.set_mode(restore_mode)
                logger.info(
                    "Plana quiet_hours ended (%s): restored to %s",
                    self.quiet_hours,
                    restore_mode,
                )

    async def _run_memory_maintenance(self) -> None:
        scopes = self._memory_maintenance_scopes()
        pushed = 0
        failed = 0
        last_error = ""
        details: list[dict[str, object]] = []
        for scope_id in scopes:
            try:
                result = await self.runtime.memory_kernel.maintain(
                    scope_id,
                    None,
                    consolidate=True,
                    decay=True,
                    accumulate=False,
                    push_warehouse=True,
                )
            except Exception:  # noqa: BLE001
                failed += 1
                last_error = f"scope {scope_id} failed"
                details.append(
                    {
                        "scope": scope_id,
                        "ok": False,
                        "error": last_error,
                    }
                )
                logger.debug(
                    "Plana maintenance: scope %s failed",
                    scope_id,
                    exc_info=True,
                )
                continue
            warehouse = result.get("warehouse")
            if isinstance(warehouse, dict) and warehouse.get("ok"):
                pushed += 1
            elif isinstance(warehouse, dict) and warehouse.get("error"):
                last_error = str(warehouse.get("error") or "")[:160]
            details.append(
                {
                    "scope": scope_id,
                    "ok": True,
                    "consolidate": result.get("consolidate", {}),
                    "decay": result.get("decay", {}),
                    "warehouse": warehouse if isinstance(warehouse, dict) else {},
                }
            )
        self.runtime.memory_maintenance_last_run = {
            "ran_at": int(time()),
            "scope_count": len(scopes),
            "warehouse_pushed": pushed,
            "failed": failed,
            "last_error": last_error,
            "scopes": details[:20],
        }
        logger.debug(
            "Plana maintenance: memory scopes=%d warehouse_pushed=%d failed=%d",
            len(scopes),
            pushed,
            failed,
        )
        if scopes and failed == len(scopes):
            raise RuntimeError(
                f"memory_maintenance_all_scopes_failed:{failed}"
            )

    def _memory_maintenance_scopes(self) -> list[str]:
        scopes = ["global"]
        active_scopes = getattr(self.runtime.storage, "active_memory_scopes", None)
        if callable(active_scopes):
            try:
                scopes.extend(active_scopes(12, since_ts=int(time()) - 30 * 86400))
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Plana maintenance: active scope lookup failed",
                    exc_info=True,
                )
        seen: set[str] = set()
        result: list[str] = []
        for scope_id in scopes:
            scope = str(scope_id or "global").strip()[:200]
            if not scope or scope in seen:
                continue
            seen.add(scope)
            result.append(scope)
        return result

    async def _run_concept_accumulation(self) -> None:
        provider = self.context.get_using_provider()
        if provider is None:
            return
        result = await self.runtime.auto_accumulate_concepts("global", provider)
        if result.get("written", 0) > 0:
            logger.info(
                "Plana maintenance: accumulate written=%d",
                result.get("written", 0),
            )

    async def _run_proactive_delivery(self) -> None:
        ready_tasks = self.runtime.proactive_queue.poll_ready(limit=5)
        if not ready_tasks:
            return
        logger.info(
            "Plana maintenance: proactive ready=%d, awaiting bridge gateway pickup",
            len(ready_tasks),
        )
