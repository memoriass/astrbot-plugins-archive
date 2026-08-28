from __future__ import annotations

from typing import Any


CONFIG_KEYS = (
    "enabled",
    "internal_lan_mode",
    "external_gateway_mode",
    "api_token",
    "core_bridge_url",
    "core_state_url",
    "core_proactive_poll_url",
    "core_proactive_deliver_url",
    "timeout_seconds",
    "enable_nacho_forward",
    "nacho_sidecar_url",
    "nacho_message_endpoint",
    "nacho_api_token",
    "listen_group",
    "listen_private",
    "listen_other",
    "send_replies",
    "proactive_poll_interval_seconds",
    "stop_pipeline_mode",
    "enable_active_send_api",
    "active_send_token",
    "enable_codex_runner",
    "codex_runner_url",
    "codex_runner_id",
    "codex_runner_lanes",
    "codex_runner_protocol_version",
    "runner_access_policy",
    "codex_runner_timeout_seconds",
    "codex_runner_submit_timeout_seconds",
    "codex_runner_delivery_concurrency",
    "codex_result_callback_url",
)


def normalize_config(config: Any) -> dict[str, Any]:
    getter = getattr(config, "get", None)
    if not callable(getter):
        return {}
    return {key: getter(key) for key in CONFIG_KEYS if getter(key) is not None}


def safe_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))
