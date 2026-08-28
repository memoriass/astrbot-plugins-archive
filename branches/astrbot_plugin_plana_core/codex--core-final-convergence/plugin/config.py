"""Configuration compatibility helpers for Plana Core."""

from __future__ import annotations

from typing import Any

_MISSING = object()

_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    "core": ("enabled", "mode", "inject_prompt", "plana_core_service_key"),
    "memory": (
        "record_messages",
        "record_llm_response",
        "max_active_memories",
        "max_active_semantics",
        "max_active_relations",
        "graph_detail_limit",
        "max_prompt_chars",
        "memory_inject_max_chars",
        "memory_inject_cooldown_seconds",
        "memory_inject_min_query_chars",
        "enable_memory_activation",
        "astrbot_kb_retrieval_enabled",
        "astrbot_kb_names",
        "astrbot_kb_trigger_terms",
        "astrbot_kb_fusion_top_k",
        "astrbot_kb_final_top_k",
        "astrbot_kb_prompt_max_chars",
        "unified_recall_enabled",
        "unified_recall_final_top_k",
        "unified_recall_prompt_max_chars",
        "unified_recall_warehouse_limit",
        "unified_recall_core_limit",
    ),
    "maintenance": (
        "enable_memory_consolidation",
        "enable_memory_decay",
        "consolidation_batch_size",
        "decay_batch_size",
        "decay_min_importance",
        "enable_auto_maintenance",
        "auto_maintenance_interval_hours",
    ),
    "task_relation": (
        "enable_relation_graph",
    ),
    "life_memory": (
        "enable_concept_extraction",
        "max_concept_keywords",
        "enable_structured_memory_extraction",
        "structured_memory_max_items",
        "enable_memory_query_planner",
        "accumulate_batch_size",
        "enable_recall_tool",
        "recall_default_k",
        "recall_max_k",
        "recall_rrf_k",
        "recall_include_semantic",
        "recall_include_concept",
    ),
    "memory_warehouse": (
        "enable_memory_warehouse",
        "memory_warehouse_url",
        "memory_warehouse_timeout_seconds",
        "memory_warehouse_push_messages",
        "memory_warehouse_push_llm_responses",
        "memory_warehouse_push_maintenance",
        "memory_warehouse_push_structured_memories",
        "memory_warehouse_push_profile_snapshots",
    ),
    "execution": (
        "assistant_task_enabled",
        "assistant_native_tool_mode",
        "assistant_low_risk_autorun",
        "assistant_long_task_threshold_seconds",
        "assistant_service_gateway_enabled",
        "assistant_service_gateway_url",
        "assistant_service_gateway_token",
        "assistant_service_gateway_timeout_seconds",
        "assistant_conversation_frame_ttl_seconds",
        "assistant_task_max_recovery_steps",
        "assistant_task_progress_enabled",
        "assistant_task_natural_confirm",
        "assistant_remote_runner_enabled",
    ),
    "ops_bridge": (
        "enable_web_dashboard",
        "debug_log",
        "enable_bridge_api",
    ),
    "gallery_media": (
        "enable_gallery_chat_images",
        "gallery_service_url",
        "gallery_timeout_seconds",
        "gallery_candidate_limit",
        "gallery_selector_threshold",
        "gallery_selector_mode",
        "gallery_reaction_frequency_mode",
        "gallery_reaction_window_size",
        "gallery_reaction_window_max",
        "gallery_direct_select_score",
        "gallery_direct_select_margin",
        "gallery_delivery_delay_ms",
        "gallery_inflight_lease_seconds",
        "gallery_reaction_scope_allowlist",
        "gallery_group_cooldown_seconds",
        "gallery_private_cooldown_seconds",
    ),
    "persona_behavior": (
        "persona_style",
        "record_all_messages",
        "enable_dialogue_wake_state",
        "dialogue_wake_words",
        "dialogue_familiar_window_seconds",
        "dialogue_observation_window_seconds",
        "assistant_behavior_orchestrator",
        "assistant_group_proactive_mode",
        "assistant_group_proactive_cooldown_seconds",
        "assistant_group_proactive_daily_limit",
        "assistant_tool_progress_threshold_seconds",
        "assistant_xiaowei_replay_shadow",
        "dialogue_poke_response",
        "dialogue_response_preflight_enabled",
        "dialogue_response_preflight_timeout_seconds",
        "dialogue_preflight_classify_chat_turns",
        "dialogue_allowed_chat_tools",
        "enable_dialogue_ledger",
        "dialogue_ledger_capacity",
        "dialogue_ledger_max_message_chars",
        "dialogue_ledger_prompt_limit",
        "quiet_hours",
        "mood_update_probability",
    ),
}

_LEGACY_KEYS = tuple(key for keys in _GROUP_KEYS.values() for key in keys)

_DEFAULT_MAINTENANCE_ALIAS = {
    "enable_auto_maintenance": False,
    "auto_maintenance_interval_hours": 6,
}


def _cfg_get(config: Any, key: str, default: Any = _MISSING) -> Any:
    getter = getattr(config, "get", None)
    if getter is None:
        return default
    try:
        return getter(key, default)
    except TypeError:
        value = getter(key)
        return default if value is None else value


def normalize_plana_config(config: Any) -> dict[str, Any]:
    """Flatten both legacy and grouped AstrBot plugin config shapes."""

    merged: dict[str, Any] = {}

    for key in _LEGACY_KEYS:
        value = _cfg_get(config, key)
        if value is not _MISSING:
            merged[key] = value

    for group, keys in _GROUP_KEYS.items():
        section = _cfg_get(config, group)
        if not hasattr(section, "get"):
            continue
        for key in keys:
            value = _cfg_get(section, key)
            if value is _MISSING:
                continue
            merged[key] = value

    legacy_ops_bridge = _cfg_get(config, "ops_bridge")
    if hasattr(legacy_ops_bridge, "get"):
        for key, default in _DEFAULT_MAINTENANCE_ALIAS.items():
            value = _cfg_get(legacy_ops_bridge, key)
            if value is not _MISSING and merged.get(key, default) == default:
                merged[key] = value

    return merged
