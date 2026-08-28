from __future__ import annotations

import json
import io
import importlib.util
import struct
import tempfile
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 500
EXPECTED_VERSION = 'version: "0.1.0-beta.1"'
EXPECTED_REPO = "https://github.com/memoriass/astrbot_plugin_plana_bridge_gateway"

EXPECTED_FILES = [
    "README.md",
    "ARCHITECTURE.md",
    "LICENSE",
    "metadata.yaml",
    "_conf_schema.json",
    "__init__.py",
    "main.py",
    "bridge/__init__.py",
    "bridge/channel_contract.md",
    "bridge/core_inprocess.py",
    "bridge/filters.py",
        "bridge/codex_relay.py",
        "bridge/idempotency.py",
    "bridge/credential.py",
    "bridge/capability.py",
    "bridge/adapters/__init__.py",
    "bridge/adapters/ani_rss.py",
    "bridge/adapters/ncqq.py",
    "bridge/adapters/qbittorrent.py",
    "bridge/adapters/komga.py",
    "bridge/adapter_registry.py",
    "scripts/import_ani_rss_credential.py",
    "bridge/proactive_delivery.py",
    "bridge/proactive_loop.py",
    "bridge/proactive_runtime.py",
    "bridge/runtime.py",
    "plugin/__init__.py",
    "plugin/config.py",
    "logo.png",
]

REQUIRED_MAIN_SNIPPETS = [
    "PAYLOAD_KINDS",
    "/plana_bridge_gateway/status",
    "/plana_bridge_gateway/bridge",
    "/plana_bridge_gateway/proactive/poll-deliver",
    "/plana_bridge_gateway/codex/result",
    "/plana_bridge_gateway/nacho/send",
    "internal_lan_mode",
    "CoreInProcessAdapter",
    "CodexRunnerRelay",
    "ProactiveDeliveryLoop",
    "ProactiveRuntimeMixin",
]

REQUIRED_CODEX_SNIPPETS = ["plana.codex.runner.v1", "/plana/codex/delegate", "/plana/codex/result/", "/plana/codex/cancel/", "/plana/codex/artifact/"]
FORBIDDEN_LEARNING_SNIPPETS = ["submit_runner_feedback", "/feedback/", "learning_candidates", "learning_context"]

REQUIRED_SCHEMA_KEYS = [
    "enabled",
    "internal_lan_mode",
    "external_gateway_mode",
    "api_token",
    "core_bridge_url",
    "core_state_url",
    "core_proactive_poll_url",
    "core_proactive_deliver_url",
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
    "credential_store_directory",
    "enable_ani_rss_adapter",
    "enable_ncqq_adapter",
    "ncqq_base_url",
    "enable_qbittorrent_adapter",
    "qbittorrent_base_url",
    "enable_komga_adapter",
    "komga_base_url",
    "ani_rss_base_url",
    "ani_rss_api_prefix",
    "ani_rss_timeout_seconds",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    check_expected_files()
    check_metadata()
    check_schema()
    check_main_contract()
    check_credential_importer()
    check_ani_rss_response_shapes()
    check_delivery_idempotency()
    check_logo()
    check_file_sizes()
    print("bridge_gateway_check=ok")


def check_expected_files() -> None:
    missing = [name for name in EXPECTED_FILES if not (ROOT / name).is_file()]
    require(not missing, f"missing_files={missing}")


def check_metadata() -> None:
    text = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    for snippet in [
        EXPECTED_VERSION,
        f'repo: "{EXPECTED_REPO}"',
        'astrbot_version: ">=4.25.0,<5.0.0"',
        "support_platforms:",
        "mcp-ready",
    ]:
        require(snippet in text, f"metadata_missing={snippet}")
    require('repo: ""' not in text, "metadata_repo_empty")


def check_schema() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_SCHEMA_KEYS if key not in schema]
    require(not missing, f"schema_missing={missing}")
    require(schema["internal_lan_mode"].get("default") is True, "internal_lan_default_not_true")
    require(schema["external_gateway_mode"].get("default") is False, "external_gateway_default_not_false")
    require(schema["enable_komga_adapter"].get("default") is False, "komga_legacy_default_not_false")
    require(
        "legacy" in schema["enable_komga_adapter"].get("description", "").casefold(),
        "komga_legacy_label_missing",
    )
    forbidden = ["core_token", "core_auth_header", "codex_runner_token"]
    present = [key for key in forbidden if key in schema]
    require(not present, f"internal_token_schema_present={present}")
    legacy_runner_keys = [key for key in schema if "hermes" in key.casefold()]
    require(not legacy_runner_keys, f"legacy_runner_schema_present={legacy_runner_keys}")
    for key in ["api_token", "active_send_token"]:
        require(schema[key].get("obvious_hint") is True, f"secret_not_marked={key}")


def check_main_contract() -> None:
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    require(
        "from .bridge import PlanaBridgeGatewayPlugin" in main_text,
        "thin_entry_missing",
    )
    text = (ROOT / "bridge" / "runtime.py").read_text(encoding="utf-8")
    proactive_text = (ROOT / "bridge" / "proactive_runtime.py").read_text(encoding="utf-8")
    auth_text = (ROOT / "bridge" / "auth.py").read_text(encoding="utf-8")
    filter_text = (ROOT / "bridge" / "filters.py").read_text(encoding="utf-8")
    missing = [snippet for snippet in REQUIRED_MAIN_SNIPPETS if snippet not in text]
    require(not missing, f"runtime_missing={missing}")
    require("external mode enabled but api_token is empty" in text, "external_token_warning_missing")
    require(
        "@filter.custom_filter(PlanaBridgeForwardFilter" in text,
        "bridge_forward_filter_missing",
    )
    require(
        "EventMessageType.ALL" not in text + filter_text,
        "bridge_event_message_type_all_present",
    )
    require("internal_lan_mode and is_loopback_request" in auth_text, "internal_loopback_auth_missing")
    require("self.core_inprocess.payload" in text, "core_payload_not_in_process_first")
    require("self.core_inprocess.poll_proactive" in text + proactive_text, "core_proactive_not_in_process_first")
    require("ProactiveRuntimeMixin" in text, "proactive_runtime_mixin_missing")
    require("self.context.send_message" not in proactive_text, "bridge_must_not_send_messages")
    require('\"notification_owner\": \"core\"' in proactive_text, "core_notification_owner_missing")
    require('core_payload.get(\"notification_sent\", False)' in proactive_text, "core_notification_result_missing")
    require("self.proactive_loop.start()" in text, "proactive_loop_not_started")
    require("secrets.compare_digest" in auth_text, "constant_time_auth_missing")
    for kind in [
        "memory_query",
        "task_delegate",
        "result_report",
        "context_sync",
        "emotional_handoff",
        "workflow_request",
    ]:
        require(kind in text, f"payload_kind_missing={kind}")
    relay_text = (ROOT / "bridge" / "codex_relay.py").read_text(encoding="utf-8")
    contract_text = (ROOT / "bridge" / "channel_contract.md").read_text(encoding="utf-8")
    delivery_text = (ROOT / "bridge" / "proactive_delivery.py").read_text(encoding="utf-8")
    require("executes_tasks" in relay_text and "relay_only" in relay_text, "codex_relay_boundary_missing")
    require("asyncio.gather" in relay_text and "DeliveryResult" in relay_text, "codex_concurrency_missing")
    require("codex_delegate" in relay_text + delivery_text, "codex_delegate_detection_missing")
    require("runner_token_configured" in relay_text and "if self.runner_token" in relay_text, "codex_token_not_optional")
    require("not payload.get(\"callback\")" in relay_text, "codex_callback_poll_boundary_missing")
    require("range(260)" in relay_text, "codex_result_poll_window_too_short")
    require("/plana/codex/artifact/" in relay_text, "codex_artifact_download_missing")
    require("artifact_integrity_mismatch" in relay_text, "codex_artifact_integrity_missing")
    require("prepare_result" in relay_text + proactive_text, "codex_artifact_prepare_missing")
    require("_report_runner_observation" in relay_text, "runner_observation_relay_missing")
    require("execution_observation" in proactive_text, "runner_observation_core_handoff_missing")
    require("event_seq" in relay_text and "heartbeat_at" in relay_text, "runner_lifecycle_fields_missing")
    require("runner_id" in relay_text and "runner_lanes" in relay_text, "runner_identity_missing")
    require("runner_protocol_version" in relay_text, "runner_protocol_version_missing")
    missing_codex = [
        snippet
        for snippet in REQUIRED_CODEX_SNIPPETS
        if snippet not in relay_text + contract_text
    ]
    require(not missing_codex, f"codex_runner_contract_missing={missing_codex}")
    learning_text = relay_text + contract_text + proactive_text + text
    forbidden_learning = [snippet for snippet in FORBIDDEN_LEARNING_SNIPPETS if snippet in learning_text]
    require(not forbidden_learning, f"runner_learning_semantics_present={forbidden_learning}")
    require(not (ROOT / "bridge" / "hermes_learning_relay.py").exists(), "hermes_learning_relay_present")
    require(not (ROOT / "bridge" / "hermes_relay.py").exists(), "hermes_relay_present")
    require((ROOT / "scripts" / "migrate_codex_runner_config.py").exists(), "codex_config_migration_missing")
    require("/plana_bridge_gateway/codex/result" in text, "codex_result_route_missing")
    require("result_report" in proactive_text and "runner_url" in proactive_text, "codex_result_ingress_missing")
    require(
        "runner_error" in relay_text and 'data.get("lane")' in relay_text,
        "codex_runner_error_detail_missing",
    )
    credential_text = (ROOT / "bridge" / "credential.py").read_text(encoding="utf-8")
    capability_text = (ROOT / "bridge" / "capability.py").read_text(encoding="utf-8")
    ani_rss_text = (ROOT / "bridge" / "adapters" / "ani_rss.py").read_text(encoding="utf-8")
    require("class CredentialProvider" in credential_text, "credential_provider_missing")
    require("hmac.compare_digest" in credential_text and "CryptProtectData" in credential_text, "credential_protection_missing")
    require("cryptography" not in credential_text, "credential_hard_dependency_present")
    require("stat.S_IRUSR | stat.S_IWUSR" in credential_text, "credential_posix_mode_missing")
    require("delegate_version" in capability_text and "action_fields_not_allowed" in capability_text, "delegate_v2_envelope_missing")
    require("service_capability_not_allowed" in capability_text, "capability_allowlist_missing")
    require("(envelope.service_ref, envelope.capability)" in capability_text, "service_capability_binding_missing")
    require("ani_rss.list_subscriptions" in ani_rss_text, "ani_rss_capability_missing")
    require("ani_rss.production" in ani_rss_text, "ani_rss_service_ref_missing")
    require('set(arguments) - {"enabled", "limit"}' in ani_rss_text, "ani_rss_argument_allowlist_missing")
    require('session.post(' in ani_rss_text and '/listAni' in ani_rss_text, "ani_rss_fixed_request_missing")
    ncqq_text = (ROOT / "bridge" / "adapters" / "ncqq.py").read_text(encoding="utf-8")
    qbittorrent_text = (ROOT / "bridge" / "adapters" / "qbittorrent.py").read_text(encoding="utf-8")
    komga_text = (ROOT / "bridge" / "adapters" / "komga.py").read_text(encoding="utf-8")
    forbidden_adapter_snippets = ["subprocess", "os.system", "create_subprocess", "shell=True"]
    adapter_text = ani_rss_text + ncqq_text + qbittorrent_text + komga_text + capability_text
    present = [snippet for snippet in forbidden_adapter_snippets if snippet in adapter_text]
    require(not present, f"adapter_shell_fallback_present={present}")
    require("capability_registry=self.capability_registry" in text, "capability_registry_not_wired")
    adapter_registry_text = (ROOT / "bridge" / "adapter_registry.py").read_text(encoding="utf-8")
    require(
        'config.get("enable_komga_adapter", False)' in adapter_registry_text,
        "komga_legacy_runtime_default_not_false",
    )
    domain_tools_text = (ROOT / "bridge" / "domain_tools.py").read_text(encoding="utf-8")
    require("plana_komga" not in domain_tools_text, "komga_tool_still_exposed")
    require("domain_harness_descriptors" not in domain_tools_text, "komga_descriptor_provider_still_exposed")
    require(not (ROOT / "bridge" / "domain_harness.py").exists(), "komga_bridge_harness_still_present")
    require("return await self._deliver_v2" in relay_text, "delegate_v2_not_dispatched")
    require("result_finalized=True" in relay_text, "delegate_v2_not_finalized")
    require('result.get("result_summary")' in relay_text, "delegate_v2_summary_not_forwarded")
    proactive_loop_text = (ROOT / "bridge" / "proactive_loop.py").read_text(encoding="utf-8")
    require("result.result_finalized" in proactive_loop_text, "finalized_result_not_propagated")
    core_adapter_text = (ROOT / "bridge" / "core_inprocess.py").read_text(encoding="utf-8")
    require("get_active_plugin" in core_adapter_text, "core_inprocess_active_plugin_missing")
    require("mark_proactive_failed" in core_adapter_text, "core_inprocess_mark_failed_missing")
    require("and not result_finalized" in core_adapter_text, "finalized_result_status_guard_missing")
    contract_text = (ROOT / "bridge" / "channel_contract.md").read_text(encoding="utf-8")
    for snippet in [
        "Normalized Incoming",
        "Capability Downgrade",
        "MCP discovery",
        "Core capability registry",
        "confirmation gate",
        "workflow event ledger",
        "human log",
        "LLM sliding history",
    ]:
        require(snippet in contract_text, f"channel_contract_missing={snippet}")


def check_credential_importer() -> None:
    importer_path = ROOT / "scripts" / "import_ani_rss_credential.py"
    importer_text = importer_path.read_text(encoding="utf-8")
    require("ProtectedFileCredentialProvider" in importer_text, "credential_import_provider_missing")
    require('data.get("api_key")' in importer_text, "credential_import_api_key_missing")
    require("source.unlink" not in importer_text, "credential_import_deletes_source")
    require("print(api_key" not in importer_text, "credential_import_prints_secret")
    spec = importlib.util.spec_from_file_location("bridge_credential_import_check", importer_path)
    require(spec is not None and spec.loader is not None, "credential_import_load_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        source = temporary / "ani-rss.json"
        store = temporary / "credentials"
        secret = "check-secret-must-not-print"
        source.write_text(json.dumps({"api_key": secret, "ignored": "value"}), encoding="utf-8-sig")
        output = io.StringIO()
        with redirect_stdout(output):
            result = module.main([str(source), str(store)])
        text = output.getvalue()
        require(result == 0, "credential_import_failed")
        require(source.is_file(), "credential_import_source_removed")
        require(secret not in text, "credential_import_secret_in_output")
        require("imported=true" in text, "credential_import_status_missing")
        require("ref=ani_rss.production.api_key" in text, "credential_import_ref_missing")
        require("source_preserved=True" in text, "credential_import_preserved_status_missing")
        encrypted = (store / "credentials.enc").read_bytes()
        require(secret.encode() not in encrypted, "credential_import_secret_not_encrypted")


def check_ani_rss_response_shapes() -> None:
    bridge_package = types.ModuleType("bridge")
    bridge_package.__path__ = [str(ROOT / "bridge")]
    adapters_package = types.ModuleType("bridge.adapters")
    adapters_package.__path__ = [str(ROOT / "bridge" / "adapters")]
    previous_bridge = sys.modules.get("bridge")
    previous_adapters = sys.modules.get("bridge.adapters")
    sys.modules["bridge"] = bridge_package
    sys.modules["bridge.adapters"] = adapters_package
    try:
        for name, path in [
            ("bridge.capability", ROOT / "bridge" / "capability.py"),
            ("bridge.credential", ROOT / "bridge" / "credential.py"),
            ("bridge.adapters.ani_rss", ROOT / "bridge" / "adapters" / "ani_rss.py"),
        ]:
            spec = importlib.util.spec_from_file_location(name, path)
            require(spec is not None and spec.loader is not None, f"module_load_failed={name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        ani_rss = sys.modules["bridge.adapters.ani_rss"]
        legacy = ani_rss._subscriptions({"data": [{"id": "legacy"}]})
        require([item.get("id") for item in legacy] == ["legacy"], "ani_rss_legacy_shape_failed")
        production = ani_rss._subscriptions(
            {
                "data": {
                    "releaseDateList": [],
                    "total": 3,
                    "weekList": [
                        {"items": [{"id": "a"}, {"id": "b"}, {"title": "no-id"}]},
                        {"items": [{"id": "a"}, {"id": "c"}]},
                    ],
                }
            }
        )
        require(
            [item.get("id") for item in production] == ["a", "b", None, "c"],
            "ani_rss_week_list_flatten_failed",
        )
        summary = ani_rss._result_summary(
            [
                {"id": "a", "enable": True, "title": "Alpha"},
                {"id": "b", "enable": False, "title": "Disabled"},
                {"id": "c", "enable": True, "name": "Charlie"},
            ],
            3,
        )
        require(summary == "ANI-RSS subscriptions: 3; enabled: Alpha, Charlie", "ani_rss_summary_failed")
        limited_summary = ani_rss._result_summary(
            [{"id": "a", "enable": True, "title": "Alpha"}],
            151,
        )
        require(
            limited_summary == "ANI-RSS subscriptions: 151; returned: 1; enabled: Alpha",
            "ani_rss_limited_summary_failed",
        )
        enabled_summary = ani_rss._result_summary(
            [
                {"enable": True, "title": "A"},
                {"enable": True, "title": "B"},
                {"enable": True, "title": "C"},
                {"enable": True, "title": "D"},
            ],
            4,
        )
        require(
            enabled_summary == "ANI-RSS subscriptions: 4; enabled: A, B, C, D",
            "ani_rss_enabled_summary_failed",
        )
        projected = ani_rss._safe_projection(
            {
                "id": "safe-id",
                "title": "Safe Title",
                "enable": True,
                "season": 2,
                "subgroup": "Group",
                "progress": 8,
                "episode": "09",
                "savePath": "C:/secret/downloads",
                "url": "https://example.invalid/private-feed",
                "api_key": "must-not-leak",
                "rules": {"huge": "raw"},
                "items": ["large", "raw", "payload"],
            }
        )
        require(
            projected
            == {
                "id": "safe-id",
                "title": "Safe Title",
                "enable": True,
                "season": 2,
                "subgroup": "Group",
                "progress": 8,
                "episode": "09",
            },
            "ani_rss_safe_projection_failed",
        )
        adapter_source = (ROOT / "bridge" / "adapters" / "ani_rss.py").read_text(encoding="utf-8")
        require("returned_count" in adapter_source, "ani_rss_returned_count_missing")
        require('"count": total' in adapter_source, "ani_rss_total_count_missing")
    finally:
        for name in ["bridge.adapters.ani_rss", "bridge.credential", "bridge.capability"]:
            sys.modules.pop(name, None)
        if previous_bridge is None:
            sys.modules.pop("bridge", None)
        else:
            sys.modules["bridge"] = previous_bridge
        if previous_adapters is None:
            sys.modules.pop("bridge.adapters", None)
        else:
            sys.modules["bridge.adapters"] = previous_adapters


def check_logo() -> None:
    data = (ROOT / "logo.png").read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), "logo_not_png")
    require(data[12:16] == b"IHDR", "logo_missing_ihdr")
    width, height = struct.unpack(">II", data[16:24])
    color_type = data[25]
    require((width, height) == (512, 512), f"logo_size={(width, height)}")
    require(color_type in {4, 6}, f"logo_no_alpha_color_type={color_type}")


def check_file_sizes() -> None:
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if ".git" in path.parts or "__pycache__" in path.parts or not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".json", ".yaml", ".yml"}:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            offenders.append(f"{path.relative_to(ROOT)}:{len(lines)}")
    require(not offenders, f"line_limit_exceeded={offenders}")


def check_delivery_idempotency() -> None:
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "bridge_idempotency_check",
        ROOT / "bridge" / "idempotency.py",
    )
    require(spec is not None and spec.loader is not None, "idempotency_module_load_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    DeliveryIdempotencyLedger = module.DeliveryIdempotencyLedger

    with tempfile.TemporaryDirectory() as tmp:
        ledger = DeliveryIdempotencyLedger(Path(tmp) / "ledger.sqlite3")
        ledger.initialize()
        payload = {
            "request_id": "request-1",
            "runner_run_id": "run-1",
            "status": "succeeded",
            "success": True,
            "summary": "done",
        }
        first = ledger.record_terminal("run-1", "succeeded", payload)
        require(first["ok"] and not first["replay"], first)
        replay = ledger.record_terminal("run-1", "succeeded", payload)
        require(replay["ok"] and replay["replay"], replay)
        conflict = ledger.record_terminal(
            "run-1",
            "failed",
            {**payload, "status": "failed", "success": False},
        )
        require(not conflict["ok"] and conflict["conflict"], conflict)
        require(ledger.mark_notification_sent("run-1"), "notification_mark_failed")
        require(not ledger.mark_notification_sent("run-1"), "notification_mark_not_idempotent")
        stored = ledger.terminal("run-1")
        require(stored is not None and bool(stored["notification_sent"]), stored)


if __name__ == "__main__":
    main()
