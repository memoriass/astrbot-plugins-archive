from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

package = ModuleType("astrbot_plugin_plana_core.web")
package.__path__ = [str(ROOT / "web")]
sys.modules["astrbot_plugin_plana_core.web"] = package
for module_name in ("capability_probe", "resource_payload", "integration_catalog"):
    spec = importlib.util.spec_from_file_location(
        f"astrbot_plugin_plana_core.web.{module_name}",
        ROOT / "web" / f"{module_name}.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

spec = importlib.util.spec_from_file_location(
    "astrbot_plugin_plana_core.web.integration_payload",
    ROOT / "web" / "integration_payload.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def main() -> None:
    capabilities = [
        {"service_ref": "komga.production", "capability": "komga.list_libraries", "read_only": True},
        {"service_ref": "komga.production", "capability": "komga.list_recent", "read_only": True},
    ]
    evidence = {
        item["capability"]: {
            "availability": "available",
            "probe_capability": "komga.list_libraries",
            "derived": item["capability"] != "komga.list_libraries",
            "checked_at": 1,
        }
        for item in capabilities
    }
    payload = module.build_integration_payload(
        gateway_url="http://192.168.1.202:8780",
        gateway_health={
            "ok": True,
            "executes_tasks": False,
            "capabilities": [
                "komga.production:komga.list_libraries",
                "komga.production:komga.list_recent",
            ],
        },
        capabilities=capabilities,
        evidence=evidence,
    )
    assert payload["gateway"]["adapter_count"] == 1
    assert payload["gateway"]["capability_count"] == 2
    assert payload["gateway"]["available_count"] == 2
    assert payload["adapters"][0]["authentication"] == "X-API-Key"
    assert payload["adapters"][0]["copy_key"] == "gateway.adapter.komga"
    assert payload["adapters"][0]["health_capability"] == "komga.list_libraries"
    assert payload["adapters"][0]["read_only_count"] == 2
    assert payload["adapters"][0]["credential_status"] == "configured"
    assert payload["adapters"][0]["capabilities"][1]["derived"] is True
    assert payload["adapters"][0]["capabilities"][1]["copy_key"] == "gateway.capability.komga_recent"
    assert payload["adapters"][0]["capabilities"][1]["arguments"][0]["name"] == "limit"

    external_payload = module.build_integration_payload(
        gateway_url="http://192.168.1.202:8780",
        gateway_health={
            "ok": True,
            "capabilities": [
                "ani_rss.production:ani_rss.download_transfer_status",
                "qbittorrent.tianxue:tianxue_qb.transfer_status",
            ],
            "resources": [
                {"service_ref": "ani_rss.production", "owner": "core", "management": "controlled"},
                {
                    "service_ref": "qbittorrent.ani",
                    "parent_service_ref": "ani_rss.production",
                    "owner": "ani_rss",
                    "management": "read_only_external",
                    "endpoint_role": "ani_rss_download",
                },
                {"service_ref": "qbittorrent.tianxue", "owner": "tianxue", "management": "read_only_external"},
            ],
        },
        capabilities=[
            {"service_ref": "ani_rss.production", "capability": "ani_rss.download_transfer_status", "read_only": True},
            {"service_ref": "qbittorrent.tianxue", "capability": "tianxue_qb.transfer_status", "read_only": True},
        ],
        evidence={
            "ani_rss.download_transfer_status": {"availability": "available", "checked_at": 1},
            "tianxue_qb.transfer_status": {"availability": "available", "checked_at": 1},
        },
    )
    external_by_ref = {item["service_ref"]: item for item in external_payload["adapters"]}
    assert external_by_ref["ani_rss.production"]["child_resources"][0]["service_ref"] == "qbittorrent.ani"
    assert external_by_ref["qbittorrent.tianxue"]["credential_status"] == "not_required"
    assert external_by_ref["qbittorrent.tianxue"]["capability_count"] == 1
    print("integration payload check passed")


if __name__ == "__main__":
    main()
