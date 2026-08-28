from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def item(schema: dict, group: str, key: str) -> dict:
    return schema[group]["items"][key]


def main() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    require("ops_voice" not in schema, "retired_voice_group_present")
    require("secretary_workflow" not in schema, "retired_secretary_group_present")
    execution = schema["execution"]["items"]
    for retired in (
        "secretary_register_llm_tool",
        "secretary_use_skill_center",
        "secretary_skill_center_url",
        "secretary_skill_center_required",
        "secretary_skill_center_timeout_seconds",
        "assistant_remote_learning_enabled",
    ):
        require(retired not in execution, f"retired_config_present={retired}")
    for retired in (
        "enable_secretary_workflows",
        "secretary_allow_local_command_execution",
        "secretary_command_backend",
        "secretary_preflight_model",
        "assistant_remote_runner_after_local_failures",
    ):
        require(retired not in execution, f"retired_execution_config_present={retired}")
    require(item(schema, "memory_warehouse", "enable_memory_warehouse").get("default") is True, "warehouse_default_disabled")
    require(item(schema, "execution", "assistant_remote_runner_enabled").get("default") is False, "runner_default_must_require_operator_enablement")
    require(item(schema, "gallery_media", "enable_gallery_chat_images").get("default") is False, "gallery_default_disabled")
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "plugin").glob("*.py"))
    for retired in ("voice_synthesis_url", "secretary_skill_center_url"):
        require(retired not in source, f"retired_runtime_config_consumer={retired}")
    print("config_defaults_check=ok")


if __name__ == "__main__":
    main()
