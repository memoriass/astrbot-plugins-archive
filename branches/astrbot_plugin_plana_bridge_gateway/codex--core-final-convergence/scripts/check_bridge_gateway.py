from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 500
EXPECTED_VERSION = 'version: "0.1.0-beta.1"'
EXPECTED_REPO = "https://github.com/memoriass/astrbot_plugin_plana_bridge_gateway"

EXPECTED_FILES = (
    "README.md",
    "ARCHITECTURE.md",
    "LICENSE",
    "metadata.yaml",
    "_conf_schema.json",
    "main.py",
    "bridge/channel_contract.md",
    "bridge/codex_relay.py",
    "bridge/core_inprocess.py",
    "bridge/filters.py",
    "bridge/idempotency.py",
    "bridge/proactive_delivery.py",
    "bridge/proactive_loop.py",
    "bridge/proactive_runtime.py",
    "bridge/runtime.py",
    "plugin/config.py",
    "logo.png",
)

RETIRED_FILES = (
    "bridge/adapter_registry.py",
    "bridge/capability.py",
    "bridge/credential.py",
    "bridge/domain_routing.py",
    "bridge/domain_tools.py",
    "bridge/adapters/__init__.py",
    "bridge/adapters/ani_rss.py",
    "bridge/adapters/ncqq.py",
    "bridge/adapters/qbittorrent.py",
    "bridge/adapters/komga.py",
    "scripts/import_ani_rss_credential.py",
    "scripts/check_domain_harness.py",
)

REQUIRED_SCHEMA_KEYS = (
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
    "proactive_poll_interval_seconds",
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

FORBIDDEN_SCHEMA_KEYS = (
    "core_token",
    "core_auth_header",
    "codex_runner_token",
    "credential_store_directory",
    "enable_ani_rss_adapter",
    "ani_rss_base_url",
    "ani_rss_api_prefix",
    "ani_rss_timeout_seconds",
    "enable_ncqq_adapter",
    "ncqq_base_url",
    "ncqq_timeout_seconds",
    "enable_qbittorrent_adapter",
    "qbittorrent_base_url",
    "qbittorrent_timeout_seconds",
    "enable_komga_adapter",
    "komga_base_url",
    "komga_timeout_seconds",
)

FORBIDDEN_PRODUCTION_MARKERS = (
    "register_llm_tool",
    "unregister_llm_tool",
    "DomainToolMixin",
    "CapabilityRegistry",
    "ActionEnvelope",
    "credential_provider",
    "capability_registry",
    "plana_qbittorrent",
    "workflow_request",
    "task_delegate",
    "learning_context",
    "submit_runner_feedback",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def tracked_sources() -> list[Path]:
    suffixes = {".py", ".js", ".css", ".html", ".md", ".json", ".yaml"}
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return sorted(
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in suffixes
            and not {".git", "__pycache__", ".ruff_cache", "tmp"}.intersection(path.parts)
        )
    return [
        ROOT / name
        for name in result.stdout.splitlines()
        if (ROOT / name).is_file() and (ROOT / name).suffix.lower() in suffixes
    ]


def check_files() -> None:
    missing = [name for name in EXPECTED_FILES if not (ROOT / name).is_file()]
    present = [name for name in RETIRED_FILES if (ROOT / name).exists()]
    require(not missing, f"missing_files={missing}")
    require(not present, f"retired_files_present={present}")


def check_metadata() -> None:
    text = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    require(EXPECTED_VERSION in text, "metadata_version_mismatch")
    require(f'repo: "{EXPECTED_REPO}"' in text, "metadata_repo_mismatch")
    require('astrbot_version: ">=4.25.0,<5.0.0"' in text, "astrbot_version_range_missing")
    require("mcp-ready" not in text, "retired_mcp_claim_present")


def check_schema() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_SCHEMA_KEYS if key not in schema]
    present = [key for key in FORBIDDEN_SCHEMA_KEYS if key in schema]
    require(not missing, f"schema_missing={missing}")
    require(not present, f"retired_schema_keys={present}")
    require(schema["internal_lan_mode"].get("default") is True, "internal_lan_default_not_true")
    require(schema["external_gateway_mode"].get("default") is False, "external_gateway_default_not_false")
    require(schema["codex_runner_protocol_version"].get("default") == "plana.codex.runner.v1", "runner_contract_mismatch")


def check_runtime_contract() -> None:
    production_files = [ROOT / "main.py", *sorted((ROOT / "bridge").rglob("*.py")), *sorted((ROOT / "plugin").rglob("*.py"))]
    source = "\n".join(path.read_text(encoding="utf-8-sig") for path in production_files)
    for marker in FORBIDDEN_PRODUCTION_MARKERS:
        require(marker not in source, f"retired_production_marker={marker}")
    runtime = (ROOT / "bridge/runtime.py").read_text(encoding="utf-8")
    for marker in (
        "PAYLOAD_KINDS",
        "/plana_bridge_gateway/status",
        "/plana_bridge_gateway/bridge",
        "/plana_bridge_gateway/proactive/poll-deliver",
        "/plana_bridge_gateway/codex/result",
        "CoreInProcessAdapter",
        "CodexRunnerRelay",
        "ProactiveDeliveryLoop",
    ):
        require(marker in runtime, f"runtime_contract_missing={marker}")
    relay = (ROOT / "bridge/codex_relay.py").read_text(encoding="utf-8")
    for marker in (
        "plana.codex.runner.v1",
        "/plana/codex/result/",
        "/plana/codex/cancel/",
        "/plana/codex/artifact/",
        '"delegate_versions": [1]',
        "unsupported_delegate_version",
    ):
        require(marker in relay, f"codex_contract_missing={marker}")
    documents = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "ARCHITECTURE.md", "bridge/channel_contract.md")
    )
    require("/plana/codex/delegate" in documents, "codex_delegate_contract_undocumented")


def check_logo() -> None:
    data = (ROOT / "logo.png").read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "logo_not_png")
    width, height = struct.unpack(">II", data[16:24])
    require(width > 0 and height > 0, "logo_dimensions_invalid")


def check_line_limits() -> None:
    oversized = []
    for path in tracked_sources():
        try:
            lines = len(path.read_text(encoding="utf-8-sig").splitlines())
        except UnicodeDecodeError:
            continue
        if lines > MAX_LINES:
            oversized.append(f"{path.relative_to(ROOT).as_posix()}:{lines}")
    require(not oversized, f"source_line_limit_exceeded={oversized}")


def main() -> None:
    check_files()
    check_metadata()
    check_schema()
    check_runtime_contract()
    check_logo()
    check_line_limits()
    print("bridge_gateway_check=ok")


if __name__ == "__main__":
    main()
