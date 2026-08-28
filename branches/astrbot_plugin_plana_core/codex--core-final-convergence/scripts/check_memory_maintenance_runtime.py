from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.memory.kernel import MemoryKernel
from astrbot_plugin_plana_core.plugin.plugin_lifecycle import PlanaPluginLifecycleMixin
from astrbot_plugin_plana_core.plugin.storage import PlanaStorage


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class WarehousePusher:
    def push_maintenance_summary(self, *_args, **_kwargs):
        return {"ok": False, "error": "warehouse unavailable"}


class MaintenanceHarness(PlanaPluginLifecycleMixin):
    def __init__(self) -> None:
        owner = self

        class Kernel:
            async def maintain(_self, scope_id, *_args, **_kwargs):
                value = owner._results[scope_id]
                if isinstance(value, Exception):
                    raise value
                return value

        self.runtime = SimpleNamespace(
            memory_kernel=Kernel(),
            memory_maintenance_last_run={},
        )

    def _memory_maintenance_scopes(self) -> list[str]:
        return list(self._results)

    async def run(self, results: dict[str, object]) -> None:
        self._results = results
        await self._run_memory_maintenance()


def check_real_storage() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = PlanaStorage(Path(temp_dir) / "plana.sqlite3")
        storage.initialize()
        for index in range(55):
            storage.upsert_semantic(
                "scope-one",
                "user:1",
                "preference",
                f"value-{index}",
                0.8,
                "acceptance",
            )
        runtime = SimpleNamespace(
            storage=storage,
            enable_memory_consolidation=False,
            enable_memory_decay=False,
            memory_warehouse_pusher=WarehousePusher(),
        )
        result = asyncio.run(
            MemoryKernel(runtime).maintain(
                "scope-one",
                None,
                consolidate=True,
                decay=True,
                push_warehouse=True,
            )
        )
        require(result["semantic_history"]["retained"] <= 50, str(result))
        require(result["warehouse"]["error"] == "warehouse unavailable", str(result))
        history = storage.semantic_history("scope-one", "user:1", "preference", 100)
        require(len(history) <= 50, f"history_not_pruned={len(history)}")


async def check_failure_reporting() -> None:
    partial = MaintenanceHarness()
    await partial.run(
        {
            "global": {"warehouse": {"ok": True}},
            "scope-two": RuntimeError("scope failed"),
        }
    )
    require(partial.runtime.memory_maintenance_last_run["failed"] == 1, "partial_failure_missing")

    complete = MaintenanceHarness()
    try:
        await complete.run(
            {
                "global": RuntimeError("global failed"),
                "scope-two": RuntimeError("scope failed"),
            }
        )
    except RuntimeError as exc:
        require("all_scopes_failed" in str(exc), str(exc))
    else:
        raise AssertionError("complete_failure_not_raised")


def main() -> None:
    check_real_storage()
    asyncio.run(check_failure_reporting())
    print("memory_maintenance_runtime_check=ok")


if __name__ == "__main__":
    main()
