from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTING_KEYS = {
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
}

BOOL_KEYS = {
    "core_service_http_enabled",
    "allow_original_path",
    "enable_commands",
    "allow_chat_image_import",
    "enable_silent_chat_image_collection",
    "tagging_ai_enabled",
}
INT_KEYS = {
    "core_service_port",
    "max_import_bytes",
    "upload_wait_seconds",
    "chat_download_timeout_seconds",
    "silent_collection_daily_limit_per_scope",
    "silent_collection_global_daily_limit",
    "silent_collection_max_images_per_message",
    "silent_collection_max_bytes",
    "silent_collection_max_pixels",
    "silent_collection_max_gif_frames",
    "tagging_confidence_threshold",
}
SECRET_KEYS = {"api_token", "core_service_key"}


def load_overrides(data_dir: str) -> dict[str, Any]:
    path = _settings_path(data_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key in SETTING_KEYS}


def save_overrides(data_dir: str, current: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    merged = {key: current[key] for key in SETTING_KEYS if key in current}
    for key, value in payload.items():
        if key in SETTING_KEYS:
            merged[key] = _coerce_value(key, value)
    path = _settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def public_settings(config: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in sorted(SETTING_KEYS):
        value = config.get(key, "")
        if key in SECRET_KEYS:
            values[f"{key}_configured"] = bool(value)
            continue
        values[key] = value
    return {
        "ok": True,
        "values": values,
        "storage": {
            "engine": "sqlite",
            "journal": "WAL",
            "tag_index": "gallery_asset_tags",
            "mode": "local_only",
        },
    }


def _settings_path(data_dir: str) -> Path:
    return Path(data_dir) / "gallery_settings.json"


def _coerce_value(key: str, value: Any) -> Any:
    if key in BOOL_KEYS:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "启用", "开启"}
        return bool(value)
    if key in INT_KEYS:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
    if key == "tagging_ai_provider":
        return str(value or "local").strip().lower()[:80] or "local"
    return str(value or "").strip()
