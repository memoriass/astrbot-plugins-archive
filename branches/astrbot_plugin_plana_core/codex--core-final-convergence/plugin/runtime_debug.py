from __future__ import annotations

from typing import Any

from ..memory import ALL_MEMORY_KINDS


def build_debug_status_payload(runtime: Any) -> dict[str, object]:
    """Build the operator/debug status payload without bloating runtime mixins."""

    return {
        "enabled": runtime.enabled,
        "mode": runtime.storage.get_state("global", runtime.mode).mode,
        "memory_activation": runtime.enable_memory_activation,
        "memory_consolidation": runtime.enable_memory_consolidation,
        "memory_decay": runtime.enable_memory_decay,
        "prompt_budget": runtime.max_prompt_chars,
        "relation_graph": runtime.enable_relation_graph,
        "graph_detail_limit": runtime.graph_detail_limit,
        "concept_extraction": runtime.enable_concept_extraction,
        "structured_memory_extraction": runtime.enable_structured_memory_extraction,
        "memory_query_planner": runtime.enable_memory_query_planner,
        "recall_tool": runtime.enable_recall_tool,
        "recall_engine": {
            "default_k": runtime.recall_default_k,
            "max_k": runtime.recall_max_k,
            "rrf_k": runtime.recall_rrf_k,
            "include_semantic": runtime.recall_include_semantic,
            "include_concept": runtime.recall_include_concept,
        },
        "memory_kinds": list(ALL_MEMORY_KINDS),
        "maintenance": runtime.maintenance.status(),
        "memory_maintenance_last_run": getattr(
            runtime,
            "memory_maintenance_last_run",
            {},
        ),
        "concept_nodes": runtime.concept_graph.storage.count_nodes(),
        "concept_edges": runtime.concept_graph.storage.count_edges(),
        "recall_gaps": runtime.recall_gap_tracker.stats("global"),
        "tables": runtime.storage.table_counts(),
        "jobs": runtime.job_manager.status(),
        "assistant_task": _status(runtime, "assistant_task_sessions"),
        "remote_task_runs": _stats(runtime, "remote_task_runs"),
        "gallery": runtime.gallery_client.status(),
        "memory_warehouse": runtime.memory_warehouse_client.local_status(),
    }


def _status(runtime: Any, attr: str) -> dict[str, object]:
    target = getattr(runtime, attr, None)
    status = getattr(target, "status", None)
    return status() if callable(status) else {}


def _stats(runtime: Any, attr: str) -> dict[str, object]:
    target = getattr(runtime, attr, None)
    stats = getattr(target, "stats", None)
    return stats() if callable(stats) else {}
