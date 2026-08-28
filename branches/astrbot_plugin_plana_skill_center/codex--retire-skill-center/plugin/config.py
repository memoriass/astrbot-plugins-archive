from __future__ import annotations

from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "register_llm_tool": False,
    "enable_write_commands": False,
    "allow_dangerous_approval": False,
    "max_skill_body_chars": 30000,
}


def normalize_skill_center_config(config: Any) -> dict[str, Any]:
    result = dict(DEFAULT_CONFIG)
    raw = {}
    if isinstance(config, dict):
        raw = config
    else:
        for key in DEFAULT_CONFIG:
            try:
                raw[key] = config.get(key)  # type: ignore[attr-defined]
            except Exception:
                continue
    result.update({key: raw[key] for key in DEFAULT_CONFIG if key in raw})
    result["enabled"] = bool(result.get("enabled", True))
    result["register_llm_tool"] = bool(result.get("register_llm_tool", False))
    result["enable_write_commands"] = bool(result.get("enable_write_commands", False))
    result["allow_dangerous_approval"] = bool(result.get("allow_dangerous_approval", False))
    result["max_skill_body_chars"] = max(
        1000,
        min(int(result.get("max_skill_body_chars") or 30000), 200000),
    )
    return result
