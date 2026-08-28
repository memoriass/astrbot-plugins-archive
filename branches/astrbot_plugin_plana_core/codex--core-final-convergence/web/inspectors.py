"""Shared payload builders for Plana Core web inspection APIs."""

from __future__ import annotations

from typing import Any

from ..memory.atom_policy import atom_final_score, atom_temporal_score
from .memory_scope_payload import memory_scope_user_id

def atom_payload(item: Any) -> dict[str, object]:
    temporal = atom_temporal_score(
        item.last_accessed_at,
        item.ttl_days,
        item.decay_type,
    )
    return {
        "id": item.id,
        "parent_memory_id": item.parent_memory_id,
        "type": item.atom_type,
        "content": item.content,
        "importance": round(float(item.importance), 3),
        "confidence": round(float(item.confidence), 3),
        "status": item.status,
        "ttl_days": round(float(item.ttl_days), 2),
        "expires_at": item.expires_at,
        "temporal_score": temporal,
        "final_score": atom_final_score(
            item.importance,
            item.confidence,
            temporal,
            item.reinforcement_count,
        ),
        "decay_type": item.decay_type,
        "reinforcement_count": item.reinforcement_count,
    }


def memory_payload(item: Any, atoms: list[Any] | None = None) -> dict[str, object]:
    payload = {
        "id": item.id,
        "kind": item.kind,
        "content": item.content,
        "importance": round(float(item.importance), 3),
        "source": item.source,
        "created_at": item.created_at,
    }
    if atoms is not None:
        payload["atoms"] = [atom_payload(atom) for atom in atoms]
    return payload


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
    search = runtime.memory_kernel.search(scope, clean_query, clean_kind, safe_limit)
    memories = search["memories"]
    semantics = search["semantics"]
    concepts = search["concepts"]
    explain = {
        "memory_route": "typed keyword search or recent memory fallback",
        "semantic_route": "semantic profile search by subject/object text",
        "concept_route": "concept graph spread activation when query exists",
        "planner": "not executed in web lab; use runtime prompt hook for LLM planning",
    }
    explain.update(search.get("explain", {}))
    return {
        "scope": scope,
        "query": query,
        "kind": kind,
        "limit": safe_limit,
        "memories": [memory_payload(item) for item in memories],
        "semantics": [semantic_payload(item) for item in semantics],
        "concepts": [concept_payload(item) for item in concepts],
        "fused_results": search.get("results", []),
        "routes": search.get("routes", {}),
        "recall_gaps": runtime.recall_gap_tracker.stats(scope)
        if hasattr(runtime, "recall_gap_tracker")
        else {},
        "explain": explain,
    }


def build_profile_payload(
    runtime: Any, scope: str = "global", limit: int = 20
) -> dict[str, object]:
    safe_limit = _limit(limit, default=20, maximum=80)
    local_semantics = list(runtime.storage.search_semantics(scope, "", safe_limit))
    user_id = _profile_user_id(runtime, scope, local_semantics, safe_limit)
    profile = runtime.memory_kernel.get_person_profile(scope, user_id, safe_limit)
    semantics = _merge_profile_semantics(
        local_semantics,
        profile["semantics"],
        user_id,
        safe_limit,
    )
    relations = profile["relations"]
    summary = dict(profile["summary"])
    summary.update(
        {
            "semantic_items": len(semantics),
            "preferences": sum(
                1 for item in semantics if item.predicate == "preference"
            ),
            "promises": sum(1 for item in semantics if item.predicate == "promise"),
        }
    )
    return {
        "scope": scope,
        "user_id": user_id,
        "summary": summary,
        "person": profile.get("person"),
        "person_summary": profile.get("person_summary", ""),
        "evidence": profile.get("evidence", []),
        "snapshots": profile.get("snapshots", []),
        "refresh": profile.get("refresh", {}),
        "semantics": [semantic_payload(item) for item in semantics],
        "relations": [relation_payload(item) for item in relations],
    }


def _profile_user_id(
    runtime: Any,
    scope: str,
    local_semantics: list[Any],
    limit: int,
) -> str:
    store = getattr(runtime, "profile_evidence_storage", None)
    if store is not None:
        evidence = store.recent_evidence(scope, "", min(limit, 20))
        snapshots = store.recent_snapshots(scope, "", 5)
        explicit_user_id = next(
            (
                str(item.get("user_id") or "").strip()
                for item in [*evidence, *snapshots]
                if str(item.get("user_id") or "").strip()
            ),
            "",
        )
        if explicit_user_id:
            return explicit_user_id

    scoped_user_id = memory_scope_user_id(scope)
    if scoped_user_id:
        return scoped_user_id

    for item in local_semantics:
        subject = str(getattr(item, "subject", "") or "").strip()
        if not subject or subject.startswith("task:"):
            continue
        subject = subject.removeprefix("user:")
        if subject:
            return subject
    return ""


def _merge_profile_semantics(
    local_semantics: list[Any],
    profile_semantics: list[Any],
    user_id: str,
    limit: int,
) -> list[Any]:
    rows = list(local_semantics)
    for item in profile_semantics:
        subject = str(getattr(item, "subject", "") or "").removeprefix("user:")
        if user_id and subject != user_id:
            continue
        rows.append(item)

    seen: set[tuple[str, str, str]] = set()
    result: list[Any] = []
    for item in rows:
        key = (
            str(getattr(item, "subject", "")),
            str(getattr(item, "predicate", "")),
            str(getattr(item, "object_value", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def build_maintenance_status_payload(runtime: Any) -> dict[str, object]:
    if not hasattr(runtime, "maintenance"):
        return {"available": False, "validation": {"status": "red", "checks": []}}
    status = runtime.maintenance.status()
    status["available"] = True
    status["jobs"] = (
        runtime.job_manager.status() if hasattr(runtime, "job_manager") else {}
    )
    status["memory_maintenance_last_run"] = getattr(
        runtime,
        "memory_maintenance_last_run",
        {},
    )
    warehouse = getattr(runtime, "memory_warehouse_client", None)
    status["memory_warehouse"] = (
        warehouse.local_status() if warehouse is not None else {}
    )
    status["patterns"] = {
        "validator": "Schema validation and index health status",
        "backup": "Persistent safety snapshot before maintenance operations",
        "scheduler": "Lifecycle-owned maintenance loop",
        "ops_gate": "Narrow operations surface for low-risk maintenance",
    }
    return status


def build_bridge_status_payload(runtime: Any) -> dict[str, object]:
    return {
        "status": runtime.bridge_contract.status(),
        "supported_kinds": [
            "memory_query",
            "execution_observation",
            "result_report",
            "context_sync",
            "emotional_handoff",
        ],
        "plugin": "astrbot_plugin_plana_bridge_gateway",
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
        "memory_inject": {
            "max_chars": getattr(runtime, "memory_inject_max_chars", 0),
            "cooldown_seconds": getattr(
                runtime,
                "memory_inject_cooldown_seconds",
                0,
            ),
            "min_query_chars": getattr(runtime, "memory_inject_min_query_chars", 0),
        },
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
