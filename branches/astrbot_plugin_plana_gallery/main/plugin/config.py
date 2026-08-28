from __future__ import annotations

from typing import Any


CONFIG_KEYS = (
    "enabled",
    "api_token",
    "core_service_http_enabled",
    "core_service_port",
    "core_service_key",
    "max_import_bytes",
    "allow_original_path",
    "enable_commands",
    "allow_chat_image_import",
    "upload_wait_seconds",
    "chat_download_timeout_seconds",
    "enable_silent_chat_image_collection",
    "silent_collection_scope_allowlist",
    "silent_collection_daily_limit_per_scope",
    "silent_collection_global_daily_limit",
    "silent_collection_max_images_per_message",
    "silent_collection_max_bytes",
    "silent_collection_max_pixels",
    "silent_collection_max_gif_frames",
    "tagging_ai_enabled",
    "tagging_ai_provider",
    "tagging_confidence_threshold",
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


def tags(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def emotions(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("emotion_tag") or item.get("tag") or "").strip().lower()[:80]
        if not tag.startswith("emotion:"):
            continue
        result.append(
            {
                "emotion_tag": tag,
                "intensity": safe_int(item.get("intensity"), 2, 1, 3),
                "prominence": "primary" if str(item.get("prominence")) == "primary" else "secondary",
                "source": str(item.get("source") or "manual")[:32],
                "suggestion_confidence": item.get("suggestion_confidence"),
            }
        )
    return result
