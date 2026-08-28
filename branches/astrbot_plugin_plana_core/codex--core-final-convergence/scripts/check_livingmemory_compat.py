from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package(PKG, ROOT)
_ensure_package(f"{PKG}.plugin", ROOT / "plugin")
compat = _load(
    f"{PKG}.plugin.livingmemory_compat",
    ROOT / "plugin" / "livingmemory_compat.py",
)


class FakeKernel:
    def __init__(self) -> None:
        self._last_prompt_context = {"scope|user:1": (123, "query")}

    def stats(self, scope: str, user_id: str) -> dict[str, object]:
        return {
            "scope": scope,
            "counts": {
                "episodic": 2,
                "semantic": 1,
                "tool_user": 1,
                "decay_events": 0,
            },
            "recall_gaps": {"open": 1, "candidate": 0, "resolved": 2},
            "user_id": user_id,
        }

    def search(self, scope: str, query: str, kind: str, limit: int) -> dict[str, object]:
        return {
            "scope": scope,
            "query": query,
            "kind": kind,
            "results": [
                {
                    "route": "atom",
                    "score": 0.91,
                    "content": f"{query} atom answer",
                }
            ],
            "memories": [
                SimpleNamespace(id=7, kind="semantic_note", content="needle memory")
            ],
        }


class FakeAtoms:
    def counts(self, scope: str) -> dict[str, int]:
        return {"total": 4, "active": 3, "expired": 1, "forgotten": 0, "scope": len(scope)}


class FakeMemoryStorage:
    def __init__(self) -> None:
        self.atoms = FakeAtoms()
        self.deleted: list[tuple[int, str]] = []

    def delete_memory(self, memory_id: int, actor: str) -> dict[str, object]:
        self.deleted.append((memory_id, actor))
        return {"ok": True, "id": memory_id}


class FakeMaintenance:
    def __init__(self) -> None:
        self.cleaned = False

    def validate(self) -> dict[str, object]:
        return {"status": "green"}

    def backup(self, reason: str) -> dict[str, object]:
        return {"ok": True, "path": f"/tmp/{reason}.sqlite3"}

    def rebuild_indexes(self) -> dict[str, object]:
        return {"ok": True, "count": 3}

    def clean_orphans(self, actor: str) -> dict[str, object]:
        self.cleaned = True
        return {"ok": True, "cleaned": 2, "actor": actor}


class FakeRuntime:
    def __init__(self) -> None:
        self.memory_kernel = FakeKernel()
        self.memory_storage = FakeMemoryStorage()
        self.maintenance = FakeMaintenance()
        self.config = {}
        self.concept_graph = SimpleNamespace(
            storage=SimpleNamespace(count_nodes=lambda: 2, count_edges=lambda: 1)
        )

    def identity_from_event(self, event) -> SimpleNamespace:
        return SimpleNamespace(global_user_id="user:1")

    def resolve_scope(self, scope: str) -> str:
        return "scope" if scope == "alias" else scope

    def consolidate_text(self, event) -> str:
        return f"consolidated:{event.unified_msg_origin}"

    async def auto_accumulate_concepts(self, scope: str, provider) -> dict[str, int]:
        return {"processed": 3, "written": 2, "skipped": 1, "provider": int(provider is not None)}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


async def main() -> None:
    runtime = FakeRuntime()
    event = SimpleNamespace(unified_msg_origin="alias")
    status = await compat.livingmemory_compat_text(runtime, event, "status", "")
    require("episodic=2" in status and "atoms=4" in status, status)
    search = await compat.livingmemory_compat_text(runtime, event, "search", "needle 2")
    require("needle atom answer" in search and "needle memory" in search, search)
    forget_preview = await compat.livingmemory_compat_text(runtime, event, "forget", "7")
    require("需要确认边界" in forget_preview, forget_preview)
    forget = await compat.livingmemory_compat_text(runtime, event, "forget", "7 confirm")
    require("已删除" in forget and runtime.memory_storage.deleted[0][0] == 7, forget)
    rebuild = await compat.livingmemory_compat_text(runtime, event, "rebuild-index", "")
    require("indexes=3" in rebuild, rebuild)
    graph = await compat.livingmemory_compat_text(
        runtime,
        event,
        "rebuild-graph",
        "",
        provider=object(),
    )
    require("written=2" in graph, graph)
    webui = await compat.livingmemory_compat_text(runtime, event, "webui", "")
    require("/api/plug/plana/dashboard" in webui and "独立管理端" not in webui, webui)
    summarize = await compat.livingmemory_compat_text(runtime, event, "summarize", "")
    require(summarize == "consolidated:alias", summarize)
    reset = await compat.livingmemory_compat_text(runtime, event, "reset", "")
    require("removed=1" in reset, reset)
    cleanup = await compat.livingmemory_compat_text(runtime, event, "cleanup", "exec")
    require("cleaned=2" in cleanup and runtime.maintenance.cleaned, cleanup)
    help_text = await compat.livingmemory_compat_text(runtime, event, "help", "")
    require("/lmem search" in help_text and "/lmem cleanup" in help_text, help_text)
    print("livingmemory_compat_check=ok")


if __name__ == "__main__":
    asyncio.run(main())
