from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READ_CAPABILITIES = {
    "komga.list_libraries",
    "komga.list_recent",
    "komga.search_series",
}
WRITE_CAPABILITIES = {
    "komga.analyze_library",
    "komga.refresh_library_metadata",
    "komga.refresh_series_metadata",
    "komga.scan_library",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    domain_tools = (ROOT / "bridge" / "domain_tools.py").read_text(encoding="utf-8")
    domain_routing = (ROOT / "bridge" / "domain_routing.py").read_text(encoding="utf-8")
    adapter = (ROOT / "bridge" / "adapters" / "komga.py").read_text(encoding="utf-8")
    registry = (ROOT / "bridge" / "adapter_registry.py").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))

    require(not (ROOT / "bridge" / "domain_harness.py").exists(), "komga_bridge_harness_still_present")
    for forbidden in (
        "plana_komga",
        "komga_plugin",
        "KomgaDomainTool",
        "domain_harness_descriptors",
        "propose_domain_action",
        "_plana_komga_read",
    ):
        require(forbidden not in domain_tools, f"komga_domain_surface_present={forbidden}")
    require("route_komga_read" not in domain_routing, "komga_natural_language_route_present")

    require(schema["enable_komga_adapter"].get("default") is False, "komga_legacy_default_not_false")
    require("legacy" in schema["enable_komga_adapter"].get("description", "").casefold(), "komga_legacy_label_missing")
    require('config.get("enable_komga_adapter", False)' in registry, "komga_legacy_runtime_default_not_false")
    require("for capability in adapter.capabilities" in registry, "komga_legacy_allowlist_not_adapter_owned")
    require("class KomgaReadOnlyAdapter" in adapter, "komga_legacy_adapter_missing")
    for capability in READ_CAPABILITIES:
        require(capability in adapter, f"komga_legacy_read_missing={capability}")
    for capability in WRITE_CAPABILITIES:
        require(capability not in adapter + registry, f"komga_legacy_write_present={capability}")
    require("read_only" in adapter, "komga_legacy_read_only_marker_missing")
    print("komga_legacy_compatibility_check=ok")


if __name__ == "__main__":
    main()
