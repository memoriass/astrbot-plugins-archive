from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import types


ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


for package_name, package_path in (
    (PKG, ROOT),
    (f"{PKG}.memory", ROOT / "memory"),
    (f"{PKG}.plugin", ROOT / "plugin"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package

Database = load_module(f"{PKG}.plugin.db", ROOT / "plugin" / "db.py").Database
load_module(f"{PKG}.memory.models", ROOT / "memory" / "models.py")
load_module(f"{PKG}.memory.atom_policy", ROOT / "memory" / "atom_policy.py")
load_module(f"{PKG}.memory.search_index", ROOT / "memory" / "search_index.py")
load_module(f"{PKG}.memory.atoms", ROOT / "memory" / "atoms.py")
load_module(f"{PKG}.memory.audit", ROOT / "memory" / "audit.py")
load_module(f"{PKG}.memory.migrations", ROOT / "memory" / "migrations.py")
load_module(f"{PKG}.memory.storage_query", ROOT / "memory" / "storage_query.py")
MemoryStorage = load_module(
    f"{PKG}.memory.storage", ROOT / "memory" / "storage.py"
).MemoryStorage
AstrBotKnowledgeAdapter = load_module(
    f"{PKG}.memory.knowledge_adapter", ROOT / "memory" / "knowledge_adapter.py"
).AstrBotKnowledgeAdapter


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeKBManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def retrieve(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "results": [
                {
                    "kb_name": "基础插件指南",
                    "doc_name": "工具注册.md",
                    "content": "使用公开 ToolSet 注册受控工具。",
                    "score": 0.93,
                }
            ]
        }


class FailingKBManager:
    async def retrieve(self, **kwargs):
        raise ConnectionError("embedding unavailable")


async def check_adapter() -> None:
    manager = FakeKBManager()
    context = SimpleNamespace(kb_manager=manager)
    adapter = AstrBotKnowledgeAdapter(
        context,
        {
            "astrbot_kb_retrieval_enabled": True,
            "astrbot_kb_names": "基础插件指南",
            "astrbot_kb_prompt_max_chars": 600,
        },
    )
    require(
        not adapter.should_retrieve("你还记得我之前喜欢什么吗", profile="chat"),
        "personal memory query must not use document RAG",
    )
    require(
        adapter.should_retrieve("AstrBot 插件工具接口文档怎么注册", profile="chat"),
        "technical document query should use AstrBot KB",
    )
    block = await adapter.prompt_block("AstrBot 插件工具接口文档怎么注册")
    require("AstrBot knowledge references" in block, f"missing block={block}")
    require("基础插件指南 / 工具注册.md" in block, f"missing source={block}")
    require(len(block) <= 600, f"budget exceeded={len(block)}")
    require(len(manager.calls) == 1, f"unexpected calls={manager.calls}")
    require(
        manager.calls[0]["kb_names"] == ["基础插件指南"],
        f"kb allowlist mismatch={manager.calls[0]}",
    )
    failing = AstrBotKnowledgeAdapter(
        SimpleNamespace(kb_manager=FailingKBManager()),
        {
            "astrbot_kb_retrieval_enabled": True,
            "astrbot_kb_names": "基础插件指南",
        },
    )
    failure_block = await failing.prompt_block("查询插件接口文档")
    require(
        "could not be retrieved" in failure_block,
        f"retrieval failure hidden={failure_block}",
    )
    require(
        "Do not claim" in failure_block,
        f"missing anti-hallucination boundary={failure_block}",
    )


def check_semantic_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = MemoryStorage(Database(Path(temp_dir) / "plana.sqlite3"))
        storage.initialize()
        storage.upsert_semantic(
            "global", "user:1", "meal_preference", "清淡", 0.72, "user_message"
        )
        storage.upsert_semantic(
            "global", "user:1", "meal_preference", "清淡", 0.86, "user_message"
        )
        storage.upsert_semantic(
            "global", "user:1", "meal_preference", "偏辣", 0.68, "user_correction"
        )
        current = storage.search_semantics("global", "偏辣", 5)
        require(current and current[0].object_value == "偏辣", f"current={current}")
        require(
            abs(current[0].confidence - 0.68) < 0.001,
            f"old confidence leaked into replacement={current[0].confidence}",
        )
        history = storage.semantic_history(
            "global", "user:1", "meal_preference", limit=10
        )
        events = [item["event_type"] for item in history]
        require("reinforced" in events, f"missing reinforcement={history}")
        require("superseded" in events, f"missing supersession={history}")
        superseded = next(item for item in history if item["event_type"] == "superseded")
        require(
            superseded["replacement_value"] == "偏辣",
            f"replacement not recorded={superseded}",
        )


def main() -> None:
    asyncio.run(check_adapter())
    check_semantic_lifecycle()
    print("astrbot_kb_memory_lifecycle_check=ok")


if __name__ == "__main__":
    main()
