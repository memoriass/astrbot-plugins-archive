"""Shared payload builders for Plana Core web inspection APIs."""

from __future__ import annotations

from typing import Any


def memory_payload(item: Any) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "content": item.content,
        "importance": round(float(item.importance), 3),
        "source": item.source,
        "created_at": item.created_at,
    }


def semantic_payload(item: Any) -> dict[str, object]:
    return {
        "id": item.id,
        "subject": item.subject,
        "predicate": item.predicate,
        "object_value": item.object_value,
        "confidence": round(float(item.confidence), 3),
        "source": item.source,
        "updated_at": item.updated_at,
    }


def concept_payload(item: Any) -> dict[str, object]:
    return {
        "id": item.id,
        "concept": item.concept,
        "weight": round(float(item.weight), 3),
        "memory_items": item.memory_items,
        "created_at": item.created_at,
        "last_modified": item.last_modified,
    }


def relation_payload(item: Any) -> dict[str, object]:
    return {
        "id": item.id,
        "source_id": item.source_id,
        "target_id": item.target_id,
        "relation_type": item.relation_type,
        "weight": round(float(item.weight), 3),
        "confidence": round(float(item.confidence), 3),
        "evidence": item.evidence,
        "updated_at": item.updated_at,
    }


def _limit(value: int, default: int = 8, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _memories(runtime: Any, scope: str, query: str, kind: str, limit: int) -> list[Any]:
    storage = runtime.storage
    if kind and query:
        return storage.search_memories_by_kind(scope, query, kind, limit)
    if kind:
        return storage.recent_memories_by_kind(scope, kind, limit)
    if query:
        return storage.search_memories(scope, query, limit)
    return storage.recent_memories(scope, limit)


def _semantics(runtime: Any, scope: str, query: str, limit: int) -> list[Any]:
    if not hasattr(runtime.storage, "search_semantics"):
        return []
    return runtime.storage.search_semantics(scope, query, limit)


def _concepts(runtime: Any, query: str, limit: int) -> list[Any]:
    if query and hasattr(runtime, "_get_relevant_concepts"):
        active = runtime._get_relevant_concepts(query)  # noqa: SLF001
        if active:
            return active[:limit]
    storage = runtime.concept_graph.storage
    return storage.load_all_nodes()[:limit]


def build_retrieve_test_payload(
    runtime: Any,
    scope: str = "global",
    query: str = "",
    kind: str = "",
    limit: int = 8,
) -> dict[str, object]:
    safe_limit = _limit(limit)
    clean_query = query.strip()
    clean_kind = kind.strip()
    memories = _memories(runtime, scope, clean_query, clean_kind, safe_limit)
    semantics = _semantics(runtime, scope, clean_query, safe_limit)
    concepts = _concepts(runtime, clean_query, safe_limit)
    recall = (
        runtime.recall_memory(scope, clean_query, clean_kind, safe_limit)
        if hasattr(runtime, "recall_memory")
        else {"results": [], "routes": {}, "explain": {}}
    )
    explain = {
        "memory_route": "typed keyword search or recent memory fallback",
        "semantic_route": "semantic profile search by subject/object text",
        "concept_route": "concept graph spread activation when query exists",
        "planner": "not executed in web lab; use runtime prompt hook for LLM planning",
    }
    explain.update(recall.get("explain", {}))
    return {
        "scope": scope,
        "query": query,
        "kind": kind,
        "limit": safe_limit,
        "memories": [memory_payload(item) for item in memories],
        "semantics": [semantic_payload(item) for item in semantics],
        "concepts": [concept_payload(item) for item in concepts],
        "fused_results": recall.get("results", []),
        "routes": recall.get("routes", {}),
        "recall_gaps": runtime.recall_gap_tracker.stats(scope)
        if hasattr(runtime, "recall_gap_tracker")
        else {},
        "explain": explain,
    }


def build_profile_payload(
    runtime: Any, scope: str = "global", limit: int = 20
) -> dict[str, object]:
    safe_limit = _limit(limit, default=20, maximum=80)
    semantics = _semantics(runtime, scope, "user:", safe_limit)
    relations = runtime.storage.related_edges("plana:core", safe_limit)
    preference_count = sum(1 for item in semantics if item.predicate == "preference")
    promise_count = sum(1 for item in semantics if item.predicate == "promise")
    return {
        "scope": scope,
        "summary": {
            "semantic_items": len(semantics),
            "relationship_edges": len(relations),
            "preferences": preference_count,
            "promises": promise_count,
        },
        "semantics": [semantic_payload(item) for item in semantics],
        "relations": [relation_payload(item) for item in relations],
    }


def build_maintenance_status_payload(runtime: Any) -> dict[str, object]:
    if not hasattr(runtime, "maintenance"):
        return {"available": False, "validation": {"status": "red", "checks": []}}
    status = runtime.maintenance.status()
    status["available"] = True
    status["patterns"] = {
        "validator": "Schema validation and index health status",
        "backup": "Persistent safety snapshot before maintenance operations",
        "scheduler": "Lifecycle-owned maintenance loop",
        "ops_gate": "Narrow operations surface for low-risk maintenance",
    }
    return status


def build_bridge_status_payload(runtime: Any) -> dict[str, object]:
    return {
        "status": runtime.arona_contract.status(),
        "supported_kinds": [
            "memory_query",
            "task_delegate",
            "result_report",
            "context_sync",
            "emotional_handoff",
        ],
        "plugin": "astrbot_plugin_nacho_bridge",
        "direct_runtime_dependency": False,
    }


def build_context_preview_payload(
    runtime: Any,
    scope: str = "global",
    query: str = "",
    kind: str = "",
    limit: int = 8,
) -> dict[str, object]:
    retrieve = build_retrieve_test_payload(runtime, scope, query, kind, limit)
    return {
        "scope": scope,
        "query": query,
        "max_prompt_chars": getattr(runtime, "max_prompt_chars", 0),
        "features": {
            "memory_activation": getattr(runtime, "enable_memory_activation", False),
            "memory_query_planner": getattr(
                runtime, "enable_memory_query_planner", False
            ),
            "concept_extraction": getattr(runtime, "enable_concept_extraction", False),
        },
        "selected": retrieve,
        "preview_lines": [
            "[Plana Context Preview]",
            f"query={query or '<empty>'}",
            f"memory_hits={len(retrieve['memories'])}",
            f"semantic_hits={len(retrieve['semantics'])}",
            f"concept_hits={len(retrieve['concepts'])}",
        ],
    }
