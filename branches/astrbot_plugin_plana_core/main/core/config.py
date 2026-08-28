"""Configuration compatibility helpers for Plana Core."""

from __future__ import annotations

from typing import Any

_MISSING = object()

_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    "core": ("enabled", "mode", "inject_prompt"),
    "memory": (
        "record_messages",
        "record_llm_response",
        "max_active_memories",
        "max_active_semantics",
        "max_active_relations",
        "graph_detail_limit",
        "max_prompt_chars",
        "enable_memory_activation",
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
        "enable_task_queue",
        "task_list_limit",
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
    "ops_bridge": (
        "enable_web_dashboard",
        "enable_debug_api",
        "debug_api_token",
        "debug_log",
        "enable_arona_api",
        "arona_api_token",
    ),
    "nacho_bridge": (
        "enable_nacho_bridge",
        "nacho_sidecar_url",
        "nacho_message_endpoint",
        "nacho_api_token",
        "nacho_timeout_seconds",
        "nacho_listen_group",
        "nacho_listen_private",
        "nacho_listen_other",
        "nacho_send_replies",
        "nacho_stop_pipeline_mode",
        "nacho_debug_log_payload",
        "nacho_enable_active_send_api",
        "nacho_active_send_token",
        "nacho_enable_plana_relay",
        "nacho_plana_result_endpoint",
        "nacho_plana_result_token",
    ),
    "persona_behavior": (
        "persona_style",
        "record_all_messages",
        "quiet_hours",
        "mood_update_probability",
        "enable_tts_response",
    ),
    "standalone_web": ("web_admin",),
}

_LEGACY_KEYS = tuple(key for keys in _GROUP_KEYS.values() for key in keys)

_DEFAULT_WEB_ADMIN = {
    "enabled": False,
    "host": "0.0.0.0",
    "port": 6180,
    "password": "",
}

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


def _is_default_web_admin(value: Any) -> bool:
    if not hasattr(value, "get"):
        return True
    for key, default in _DEFAULT_WEB_ADMIN.items():
        if _cfg_get(value, key, default) != default:
            return False
    return True


def normalize_plana_config(config: Any) -> dict[str, Any]:
    """Flatten both legacy and grouped AstrBot plugin config shapes."""

    merged: dict[str, Any] = {}
    legacy_web_admin = _cfg_get(config, "web_admin")

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
            if (
                group == "standalone_web"
                and key == "web_admin"
                and legacy_web_admin is not _MISSING
                and _is_default_web_admin(value)
            ):
                continue
            merged[key] = value

    legacy_ops_bridge = _cfg_get(config, "ops_bridge")
    if hasattr(legacy_ops_bridge, "get"):
        for key, default in _DEFAULT_MAINTENANCE_ALIAS.items():
            value = _cfg_get(legacy_ops_bridge, key)
            if value is not _MISSING and merged.get(key, default) == default:
                merged[key] = value

    return merged
