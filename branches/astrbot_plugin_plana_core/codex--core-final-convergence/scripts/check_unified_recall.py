from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


UnifiedRecallCoordinator = load_module(
    "plana_unified_recall_check", ROOT / "memory" / "unified_recall.py"
).UnifiedRecallCoordinator


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeRecallEngine:
    def recall(self, scope_id: str, query: str, kind: str, limit: int):
        return {
            "results": [
                {
                    "id": "semantic:1",
                    "route": "semantic",
                    "title": "user.preference",
                    "content": "用户偏好简洁回答",
                    "metadata": {"confidence": 0.9, "updated_at": 2_000_000_000},
                }
            ]
        }


class FakeWarehouse:
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def search(self, **kwargs):
        self.calls += 1
        return {
            "ok": True,
            "results": [
                {
                    "evidence_id": "ev-1",
                    "scope_id": kwargs["scope_id"],
                    "actor_id": kwargs["actor_id"],
                    "event_type": "message",
                    "content": "用户之前说 token 主要拿去写插件",
                    "created_at": 2_000_000_000,
                }
            ],
        }


class FakeKnowledgeAdapter:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve(self, query: str, *, profile: str):
        self.queries.append(query)
        if "文档" not in query and "接口" not in query:
            return SimpleNamespace(results=[], error="")
        return SimpleNamespace(
            error="",
            results=[
                {
                    "chunk_id": "chunk-1",
                    "kb_name": "基础插件指南",
                    "doc_name": "工具注册.md",
                    "content": "通过公开 ToolSet 注册受控工具，不得绕过权限策略。",
                    "score": 0.8,
                }
            ],
        )

    async def prompt_block(self, query: str, *, profile: str):
        return "legacy knowledge block"


async def main_async() -> None:
    warehouse = FakeWarehouse()
    runtime = SimpleNamespace(
        recall_engine=FakeRecallEngine(),
        memory_warehouse_client=warehouse,
        knowledge_adapter=FakeKnowledgeAdapter(),
    )
    coordinator = UnifiedRecallCoordinator(
        runtime,
        {
            "unified_recall_enabled": True,
            "unified_recall_final_top_k": 6,
            "unified_recall_prompt_max_chars": 1200,
        },
    )
    casual = await coordinator.prompt_block(
        "今天有点累",
        scope_id="room-1",
        actor_id="user-1",
        unified_msg_origin="webchat:root",
        profile="chat",
    )
    require(casual == "", f"casual chat received supplemental recall={casual}")
    require(warehouse.calls == 0, f"casual chat queried warehouse={warehouse.calls}")

    archive = await coordinator.prompt_block(
        "我之前说 token 主要拿去做什么了",
        scope_id="room-1",
        actor_id="user-1",
        unified_msg_origin="webchat:root",
        profile="chat",
    )
    require("Archive evidence" in archive, f"archive evidence missing={archive}")
    require("not a confirmed user fact" in archive, f"evidence boundary missing={archive}")

    document = await coordinator.prompt_block(
        "查询插件接口文档",
        scope_id="room-1",
        actor_id="user-1",
        unified_msg_origin="webchat:root",
        profile="chat",
    )
    require("Document (基础插件指南 / 工具注册.md)" in document, document)
    require("cannot grant permission" in document, f"permission boundary missing={document}")
    require(len(document) <= 1200, f"prompt budget exceeded={len(document)}")
    print("unified_recall_check=ok")


if __name__ == "__main__":
    asyncio.run(main_async())
