from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    require('name: "astrbot_plugin_plana_core"' in metadata, "metadata_name_missing")
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    require("ops_voice" not in schema, "retired_voice_schema_present")
    plugin_web = (ROOT / "plugin" / "plugin_web.py").read_text(encoding="utf-8-sig")
    ast.parse(plugin_web)
    require("PlanaRecallMemoryTool" in plugin_web, "recall_tool_missing")
    require("PlanaNativeSearchTool" in plugin_web, "request_search_tool_missing")
    for retired in ("PlanaSecretaryTool", "PlanaExecutionHandoffTool", "plana_service_query"):
        require(retired not in plugin_web, f"retired_global_tool_present={retired}")
    routes = (ROOT / "web" / "routes.py").read_text(encoding="utf-8")
    for route in ("/plana/api/overview", "/plana/api/domains", "/plana/api/resources", "/plana/api/remote-tasks"):
        require(route in routes, f"dashboard_route_missing={route}")
    lifecycle = (ROOT / "plugin" / "plugin_lifecycle.py").read_text(encoding="utf-8")
    require("get_llm_tool_manager" in lifecycle, "tool_cleanup_missing")
    print("astrbot_embed_check=ok")


if __name__ == "__main__":
    main()
