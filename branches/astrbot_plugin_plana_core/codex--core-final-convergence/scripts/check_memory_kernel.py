from __future__ import annotations

import sys
import importlib.util
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
_ensure_package(f"{PKG}.memory", ROOT / "memory")
_ensure_package(f"{PKG}.identity", ROOT / "identity")
_ensure_package(f"{PKG}.relation", ROOT / "relation")
_ensure_package(f"{PKG}.plugin", ROOT / "plugin")
plugin_storage = types.ModuleType(f"{PKG}.plugin.storage")
plugin_storage.PlanaStorage = object
sys.modules[f"{PKG}.plugin.storage"] = plugin_storage
_load(f"{PKG}.identity.models", ROOT / "identity" / "models.py")
memory_models = _load(f"{PKG}.memory.models", ROOT / "memory" / "models.py")
memory_classifier = _load(f"{PKG}.memory.classifier", ROOT / "memory" / "classifier.py")
_load(f"{PKG}.memory.recall_gap_service", ROOT / "memory" / "recall_gap_service.py")
MemoryKernel = _load(f"{PKG}.memory.kernel", ROOT / "memory" / "kernel.py").MemoryKernel
ProfileScanner = _load(
    f"{PKG}.relation.profile_scanner",
    ROOT / "relation" / "profile_scanner.py",
).ProfileScanner
StructuredMemoryItem = memory_classifier.StructuredMemoryItem
LLMStructuredMemoryExtractor = memory_classifier.LLMStructuredMemoryExtractor
MEMORY_KIND_USER_FACT = memory_models.MEMORY_KIND_USER_FACT
MEMORY_KIND_USER_PREFERENCE = memory_models.MEMORY_KIND_USER_PREFERENCE


class FakeStorage:
    def __init__(self) -> None:
        self.memories: list[SimpleNamespace] = []
        self.semantics: list[SimpleNamespace] = []

    def add_memory(
        self,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
        **metadata,
    ) -> None:
        memory_id = len(self.memories) + 1
        self.memories.append(
            SimpleNamespace(
                id=memory_id,
                scope=scope,
                scope_id=scope_id,
                kind=kind,
                content=content,
                importance=importance,
                source=source,
                created_at=1,
                actor_id=str(metadata.get("actor_id", "")),
                subject=str(metadata.get("subject", "")),
            )
        )
        return memory_id

    def upsert_semantic(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
    ) -> None:
        self.semantics.append(
            SimpleNamespace(
                id=len(self.semantics) + 1,
                scope_id=scope_id,
                subject=subject,
                predicate=predicate,
                object_value=object_value,
                confidence=confidence,
                source=source,
                updated_at=1,
            )
        )

    def search_memories_by_kind(self, scope: str, query: str, kind: str, limit: int):
        return [
            item
            for item in self.memories
            if item.scope_id == scope and item.kind == kind and query in item.content
        ][:limit]

    def recent_memories_by_kind(self, scope: str, kind: str, limit: int):
        return [
            item for item in self.memories if item.scope_id == scope and item.kind == kind
        ][:limit]

    def search_memories(self, scope: str, query: str, limit: int):
        return [
            item for item in self.memories if item.scope_id == scope and query in item.content
        ][:limit]

    def recent_memories(self, scope: str, limit: int):
        return [item for item in self.memories if item.scope_id == scope][:limit]

    def search_semantics(self, scope: str, query: str, limit: int):
        return [
            item
            for item in self.semantics
            if item.scope_id == scope
            and (not query or query in item.subject or query in item.object_value)
        ][:limit]

    def related_edges(self, _node: str, _limit: int, _scope_id: str | None = None):
        return []

    def memory_counts(self, scope: str, _user_id: str):
        return {
            "episodic": len([item for item in self.memories if item.scope_id == scope]),
            "semantic": len([item for item in self.semantics if item.scope_id == scope]),
            "tool_user": 0,
            "decay_events": 0,
        }


class FakeRecallEngine:
    def recall(self, scope: str, query: str, kind: str, limit: int) -> dict[str, object]:
        return {
            "results": [{"route": "memory", "scope": scope, "query": query, "kind": kind}],
            "routes": {"memory": 1},
            "explain": {"limit": limit},
        }


class FakeFeedbackQueue:
    def stats(self, scope: str) -> dict[str, int]:
        return {"pending": 0, "processed": 0, "scope_len": len(scope)}


class FakeRecallGapTracker:
    def __init__(self) -> None:
        self.gaps: list[tuple[str, str, str]] = []

    def record_gap(self, scope: str, user_id: str, query: str) -> None:
        self.gaps.append((scope, user_id, query))

    def stats(self, scope: str) -> dict[str, int]:
        return {"open": len([item for item in self.gaps if item[0] == scope])}


class FakePersonInfoStorage:
    def get(self, _user_id: str, _scope: str):
        return None


class FakeMemoryActivator:
    def __init__(self, storage: FakeStorage) -> None:
        self.storage = storage

    def activate(self, _query: str, scope: str, _identity, relations):
        return SimpleNamespace(
            memories=self.storage.search_memories(scope, "precise", 10),
            semantics=self.storage.search_semantics(scope, "user:1", 10),
            relations=relations,
        )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    storage = FakeStorage()
    runtime = SimpleNamespace(
        storage=storage,
        concept_graph=SimpleNamespace(storage=SimpleNamespace(load_all_nodes=lambda: [])),
        recall_engine=FakeRecallEngine(),
        recall_gap_tracker=FakeRecallGapTracker(),
        feedback_queue=FakeFeedbackQueue(),
        person_info_storage=FakePersonInfoStorage(),
        memory_activator=FakeMemoryActivator(storage),
        recall_default_k=5,
        recall_max_k=10,
        max_active_relations=1,
        max_active_semantics=1,
        max_prompt_chars=4000,
        memory_inject_max_chars=320,
        memory_inject_cooldown_seconds=60,
        memory_inject_min_query_chars=2,
        enable_memory_activation=True,
        config={},
        resolve_scope=lambda scope: "global" if scope == "alias" else scope,
    )
    kernel = MemoryKernel(runtime)
    written = kernel.ingest_text(
        "alias",
        "user:1",
        "User likes precise execution plans.",
        kind="user_preference",
        semantic_predicate="preference",
        semantic_value="precise execution plans",
    )
    require(written["stored"] and written["semantic_written"], f"write={written}")
    result = kernel.search("alias", "precise", "", 3)
    require(result["scope"] == "global", f"scope={result}")
    require(len(result["memories"]) == 1, f"memories={result}")
    require(len(result["semantics"]) == 1, f"semantics={result}")
    profile = kernel.get_person_profile("alias", "user:1", 5)
    require(profile["summary"]["preferences"] == 1, f"profile={profile}")
    stats = kernel.stats("alias", "user:1")
    require(stats["counts"]["episodic"] == 1, f"stats={stats}")
    kernel.ingest_text(
        "alias",
        "user:1",
        "precise " + ("execution planning detail " * 40),
        kind="message",
        importance=0.25,
    )
    long_text = "HEAD " + ("middle " * 260) + " TAIL"
    long_written = kernel.ingest_text("alias", "user:1", long_text, kind="message")
    long_memory = storage.memories[-1].content
    require(long_written["truncated"], f"long_write_not_truncated={long_written}")
    require(
        "HEAD" in long_memory and "TAIL" in long_memory and "truncated" in long_memory,
        f"long_memory_lost_context={long_memory}",
    )
    identity = SimpleNamespace(global_user_id="user:1")
    relations = [SimpleNamespace(source_id="user:1"), SimpleNamespace(source_id="x")]
    prompt = kernel.prompt_context("precise plans", "alias", identity, relations=relations)
    active = prompt["active_context"]
    used_chars = sum(len(item.content) for item in active.memories)
    used_chars += sum(len(item.object_value) for item in active.semantics)
    require(prompt["skipped_reason"] == "", f"prompt={prompt}")
    require(prompt["limits"]["max_chars"] == 320, f"limits={prompt['limits']}")
    require(used_chars <= 320, f"used_chars={used_chars}")
    require(len(active.relations) == 1, f"relations={active.relations}")
    cooled = kernel.prompt_context("plans precise", "alias", identity, relations=relations)
    require(cooled["skipped_reason"] == "cooldown_same_query", f"cooled={cooled}")
    require(cooled["active_context"].memories == [], f"cooled={cooled}")
    forced = kernel.prompt_context(
        "plans precise",
        "alias",
        identity,
        relations=relations,
        force=True,
    )
    require(forced["skipped_reason"] == "", f"forced={forced}")
    storage.upsert_semantic(
        "global",
        "user:1",
        "theme",
        "cross group dark theme",
        0.9,
        "profile_scanner:global",
    )
    runtime.max_active_semantics = 2
    cross_scope = kernel.prompt_context("theme", "room-a", identity, force=True)
    semantic_values = [
        getattr(item, "object_value", "") for item in cross_scope["active_context"].semantics
    ]
    require(
        "cross group dark theme" in semantic_values,
        f"cross_scope_profile_semantics_missing={semantic_values}",
    )
    scanner = ProfileScanner(storage, cooldown=0)
    scan_identity = SimpleNamespace(global_user_id="user:2")
    scanner.apply(
        "room-a",
        scan_identity,
        [
            StructuredMemoryItem(
                kind=MEMORY_KIND_USER_PREFERENCE,
                content="user prefers terse beta reports",
                subject="user:user:2",
                predicate="preference",
                object_value="terse beta reports",
            )
        ],
    )
    scanner.apply(
        "room-a",
        scan_identity,
        [
            StructuredMemoryItem(
                kind=MEMORY_KIND_USER_FACT,
                content="user is discussing room-a launch details",
                subject="user:user:2",
                predicate="current_group_topic",
                object_value="room-a launch details",
            )
        ],
    )
    scanner.apply(
        "room-a",
        scan_identity,
        [
            StructuredMemoryItem(
                kind=MEMORY_KIND_USER_FACT,
                content="user timezone is Asia/Shanghai",
                subject="user:user:2",
                predicate="timezone",
                object_value="Asia/Shanghai",
            )
        ],
    )
    global_values = [
        getattr(item, "object_value", "")
        for item in storage.semantics
        if getattr(item, "scope_id", "") == "global"
        and getattr(item, "subject", "") == "user:user:2"
    ]
    require("terse beta reports" in global_values, f"global_preference_missing={global_values}")
    require("Asia/Shanghai" in global_values, f"global_identity_fact_missing={global_values}")
    require(
        "room-a launch details" not in global_values,
        f"group_fact_leaked_to_global={global_values}",
    )
    extractor = LLMStructuredMemoryExtractor(max_items=3)
    low_items = extractor._parse_items(  # noqa: SLF001
        '{"items":[{"kind":"user_fact","content":"某用户提到了一些事情",'
        '"subject":"user:user:3","predicate":"fact","object_value":"一些事情",'
        '"summary_quality":"low","confidence":0.9,"importance":0.9}]}'
    )
    require(low_items and not low_items[0].promotable, f"low_quality_promoted={low_items}")
    normal_items = extractor._parse_items(  # noqa: SLF001
        '{"items":[{"kind":"user_preference","content":"用户偏好简洁的 beta 报告",'
        '"subject":"user:user:3","predicate":"preference",'
        '"object_value":"简洁的 beta 报告","canonical_summary":"用户偏好简洁的 beta 报告",'
        '"persona_summary":"回复时保持简洁","summary_quality":"normal",'
        '"confidence":0.9,"importance":0.8}]}'
    )
    require(normal_items and normal_items[0].promotable, f"normal_quality_blocked={normal_items}")
    require(
        normal_items[0].canonical_summary == "用户偏好简洁的 beta 报告",
        f"canonical_summary_missing={normal_items[0]}",
    )
    scanner.apply("room-a", scan_identity, low_items)
    low_global_values = [
        getattr(item, "object_value", "")
        for item in storage.semantics
        if getattr(item, "scope_id", "") == "global"
        and getattr(item, "subject", "") == "user:user:3"
    ]
    require(not low_global_values, f"low_quality_profile_promoted={low_global_values}")
    print("memory_kernel_check=ok")


if __name__ == "__main__":
    main()
