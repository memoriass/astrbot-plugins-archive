from __future__ import annotations

import asyncio
import importlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

importlib.import_module("astrbot_plugin_plana_core.service_gateway")


web_package = ModuleType("astrbot_plugin_plana_core.web")
web_package.__path__ = [str(ROOT / "web")]
sys.modules["astrbot_plugin_plana_core.web"] = web_package
spec = importlib.util.spec_from_file_location(
    "astrbot_plugin_plana_core.web.capability_probe",
    ROOT / "web" / "capability_probe.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
build_service_capability_evidence = module.build_service_capability_evidence


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def query(self, *, service_ref: str, **kwargs):
        if service_ref == "komga.production":
            return {"status": "failed", "error": "credential_not_found"}
        return {"status": "succeeded", "data": {}}


async def check() -> None:
    runtime = SimpleNamespace(
        config={
            "assistant_service_gateway_enabled": True,
            "assistant_service_gateway_url": "http://127.0.0.1:8780",
            "assistant_service_gateway_token": "test-token",
            "assistant_service_gateway_timeout_seconds": 20,
        }
    )
    capabilities = [
        {"service_ref": "ani_rss.production", "capability": "ani_rss.search_title"},
        {"service_ref": "qbittorrent.production", "capability": "qbittorrent.list_files"},
        {"service_ref": "komga.production", "capability": "komga.search_series"},
    ]
    evidence = await build_service_capability_evidence(
        runtime,
        capabilities,
        client_factory=FakeClient,
    )
    assert evidence["ani_rss.search_title"]["availability"] == "available"
    assert evidence["ani_rss.search_title"]["derived"] is True
    assert evidence["ani_rss.search_title"]["completed"] == 0
    assert evidence["ani_rss.search_title"]["probe_completed"] == 1
    assert evidence["qbittorrent.list_files"]["availability"] == "available"
    assert evidence["komga.search_series"]["availability"] == "restricted"
    assert evidence["komga.search_series"]["error"] == "credential_not_found"
    print("capability probe check passed")


if __name__ == "__main__":
    asyncio.run(check())
