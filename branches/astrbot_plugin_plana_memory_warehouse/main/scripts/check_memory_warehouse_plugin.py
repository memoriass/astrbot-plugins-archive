from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.store import (  # noqa: E402
    CONTRACT_VERSION,
    MemoryWarehouseStore,
    _like_pattern,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def check_files() -> None:
    for rel in (
        "metadata.yaml",
        "_conf_schema.json",
        "README.md",
        "ARCHITECTURE.md",
        "main.py",
        "plugin/runtime.py",
        "plugin/config.py",
        "plugin/capture.py",
        "plugin/filters.py",
        "plugin/http_api.py",
        "plugin/maintenance_api.py",
        "plugin/store.py",
        "plugin/store_common.py",
        "plugin/store_schema.py",
        "plugin/store_search.py",
        "plugin/store_maintenance.py",
    ):
        require((ROOT / rel).is_file(), f"missing_file={rel}")
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    require("api_token" not in schema, "schema_api_token_present")
    for key in (
        "enabled",
        "enable_core_api",
        "max_content_chars",
        "max_search_limit",
        "max_bulk_items",
        "allow_commands",
        "capture_messages",
        "capture_llm_responses",
        "capture_commands",
        "excluded_prefixes",
        "min_content_chars",
        "retention_days",
        "maintenance_on_start",
    ):
        require(key in schema, f"schema_key_missing={key}")
    require(schema["allow_commands"].get("default") is False, "allow_commands_default_open")
    require(schema["capture_messages"].get("default") is False, "capture_messages_default_open")
    require(
        schema["capture_llm_responses"].get("default") is False,
        "capture_llm_responses_default_open",
    )
    thin_main = (ROOT / "main.py").read_text(encoding="utf-8")
    require(
        "from .plugin.runtime import PlanaMemoryWarehousePlugin" in thin_main,
        "main_not_thin_runtime_export",
    )
    main_text = "\n".join(
        (ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            "main.py",
            "plugin/runtime.py",
            "plugin/capture.py",
            "plugin/filters.py",
            "plugin/maintenance_api.py",
        )
    )
    runtime_text = (ROOT / "plugin/runtime.py").read_text(encoding="utf-8")
    filter_text = (ROOT / "plugin/filters.py").read_text(encoding="utf-8")
    for snippet in (
        "PlanaMemoryWarehousePlugin",
        "active_warehouse",
        "@filter.custom_filter(PlanaWarehousePassiveCaptureFilter",
        "@filter.on_llm_response",
        "await plugin.capture_llm_response(event, response)",
        "/plana_warehouse/evidence/ingest",
        "/plana_warehouse/evidence/bulk-ingest",
        "/plana_warehouse/evidence/search",
        "/plana_warehouse/evidence/recent",
        "/plana_warehouse/evidence/get",
        "/plana_warehouse/maintenance/rebuild-index",
        "/plana_warehouse/maintenance/prune",
        "/plana_warehouse/maintenance/backup",
        "/plana_warehouse/maintenance/backup/validate",
        "/plana_warehouse/maintenance/restore-candidate",
        "/plana_warehouse/maintenance/delete-evidence",
        "def _is_loopback_request",
        "X-Forwarded-For",
        "X-Real-IP",
        "Forwarded",
        "remote.startswith(\"::ffff:127.\")",
        '@filter.command("plana_warehouse_status")',
        '@filter.command("plana_warehouse_search")',
        '@filter.command("plana_warehouse_recent")',
        '@filter.command("plana_warehouse_rebuild_index")',
        '@filter.command("plana_warehouse_prune")',
        "confirm_required",
        "index rebuild requires confirm",
        "origin = self._event_origin(event)",
        "origin unavailable",
        "unified_msg_origin=origin",
    ):
        require(snippet in main_text, f"main_missing={snippet}")
    for forbidden in (
        "api_token",
        "X-Plana-Warehouse-Token",
        "Authorization",
        "Bearer",
        "secrets",
    ):
        require(forbidden not in main_text, f"inline_auth_present={forbidden}")
    require(
        "@filter.event_message_type" not in runtime_text + filter_text
        and "EventMessageType.ALL" not in runtime_text + filter_text,
        "warehouse_event_message_type_all_present",
    )
    require("@filter." not in runtime_text, "runtime_should_not_hold_astrbot_filters")
    require(
        "async def capture_llm_response" in runtime_text,
        "runtime_missing_llm_response_business_method",
    )
    require(
        "return False" in filter_text.split(
            "class PlanaWarehousePassiveCaptureFilter", 1
        )[1],
        "warehouse_passive_filter_should_not_activate",
    )
    require(
        "return self._is_loopback_request()" in runtime_text,
        "api_not_loopback_only",
    )
    require(
        "response: Any | None = None" in runtime_text,
        "llm_response_hook_response_not_optional",
    )
    require(
        "if response is None:" in runtime_text,
        "llm_response_hook_missing_no_response_guard",
    )
    for rel in (
        "main.py",
        "plugin/runtime.py",
        "plugin/config.py",
        "plugin/capture.py",
        "plugin/filters.py",
        "plugin/http_api.py",
        "plugin/store.py",
        "plugin/store_common.py",
        "plugin/store_schema.py",
        "plugin/store_search.py",
        "plugin/store_maintenance.py",
    ):
        line_count = len((ROOT / rel).read_text(encoding="utf-8").splitlines())
        require(line_count <= 500, f"line_limit_exceeded={rel}:{line_count}")
    store_text = "\n".join(
        (ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            "plugin/store.py",
            "plugin/store_common.py",
            "plugin/store_schema.py",
            "plugin/store_search.py",
            "plugin/store_maintenance.py",
        )
    )
    require("plana.memory_warehouse.v1" in store_text, "store_missing_contract")
    for snippet in (
        "external_event_id",
        "def bulk_ingest(",
        "def recent(",
        "def rebuild_index(",
        "def prune(",
        "def create_backup(",
        "def validate_backup(",
        "def prepare_restore_candidate(",
        "def delete_evidence(",
        "index_consistent",
    ):
        require(snippet in store_text, f"store_missing={snippet}")


def check_store() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = MemoryWarehouseStore(tmp, max_content_chars=1000)
        store.initialize()
        result = store.ingest(
            {
                "contract_version": CONTRACT_VERSION,
                "scope_id": "scope",
                "unified_msg_origin": "origin",
                "platform": "test",
                "message_type": "GroupMessage",
                "session_id": "session",
                "group_id": "group",
                "actor_id": "user",
                "actor_name": "Alice",
                "role": "user",
                "event_type": "message",
                "content": "Plana remembers the warehouse split boundary.",
                "external_event_id": "origin:msg-1",
                "metadata": {"source": "unit"},
            }
        )
        require(result["ok"], f"ingest_failed={result}")
        evidence_id = result["evidence_id"]
        require(evidence_id.startswith("wh:"), "evidence_id_prefix")
        updated = store.ingest(
            {
                "scope_id": "scope",
                "unified_msg_origin": "origin",
                "actor_id": "user",
                "role": "user",
                "event_type": "message",
                "content": "Plana updated the warehouse split boundary.",
                "external_event_id": "origin:msg-1",
                "metadata": {"source": "retry"},
            }
        )
        require(updated["ok"] and updated["updated"], f"idempotent_update_failed={updated}")
        found = store.search(query="warehouse split", scope_id="scope", limit=5)
        require(found["ok"] and found["count"] == 1, f"search_failed={found}")
        require(found["source"] in {"fts", "hybrid"}, f"search_not_indexed={found}")
        shared_scope_hit = store.search(
            query="warehouse split",
            scope_ids=["missing", "scope"],
            actor_id="user",
            limit=5,
        )
        require(
            shared_scope_hit["ok"] and shared_scope_hit["count"] == 1,
            f"shared_scope_search_failed={shared_scope_hit}",
        )
        loaded = store.get(evidence_id)
        require(loaded is not None, "get_missing")
        require(loaded["metadata"]["source"] == "retry", "metadata_update_missing")
        bulk = store.bulk_ingest(
            [
                {
                    "scope_id": "scope",
                    "unified_msg_origin": "origin",
                    "actor_id": "user",
                    "role": "user",
                    "event_type": "message",
                    "content": "长期记忆仓库 支持中文检索。",
                    "external_event_id": "origin:msg-old",
                    "created_at": 100,
                },
                {
                    "scope_id": "scope",
                    "unified_msg_origin": "origin",
                    "actor_id": "assistant",
                    "role": "assistant",
                    "event_type": "llm_response",
                    "content": "Warehouse backup and restore boundary stays outside Core.",
                    "external_event_id": "origin:reply-1",
                },
            ]
        )
        require(bulk["ok"] and bulk["created"] == 2, f"bulk_failed={bulk}")
        recent = store.recent(scope_id="scope", limit=10)
        require(recent["count"] == 3, f"recent_count={recent}")
        chinese = store.search(query="仓库", scope_id="scope", limit=5)
        require(chinese["count"] == 1, f"chinese_like_fallback_failed={chinese}")
        rebuilt = store.rebuild_index()
        require(rebuilt["indexed"] == 3, f"rebuild_failed={rebuilt}")
        preview = store.prune(before_ts=200, limit=10, dry_run=True)
        require(preview["matched"] == 1 and preview["deleted"] == 0, f"prune_preview_failed={preview}")
        pruned = store.prune(before_ts=200, limit=10, dry_run=False)
        require(pruned["deleted"] == 1, f"prune_failed={pruned}")
        status = store.status()
        require(status["event_count"] == 2, f"status_count={status}")
        require(status["index_consistent"], f"index_inconsistent={status}")
        require("db_path" not in status, f"status_leaks_db_path={status}")
        live_hash_before = store._file_sha256(store.db_path)
        backup = store.create_backup()
        require(backup["ok"], f"backup_failed={backup}")
        require(backup["event_count"] == 2, f"backup_event_count={backup}")
        require(backup["index_consistent"], f"backup_index_inconsistent={backup}")
        require("/" not in backup["backup_name"], f"backup_name_not_bounded={backup}")
        validated = store.validate_backup(backup["backup_name"])
        require(validated["ok"], f"backup_validation_failed={validated}")
        require(validated["manifest_matches"], f"backup_manifest_mismatch={validated}")
        rejected_path = store.validate_backup("../memory_warehouse.sqlite3")
        require(
            not rejected_path["ok"] and rejected_path["error"] == "backup_not_found",
            f"backup_path_escape_allowed={rejected_path}",
        )
        candidate = store.prepare_restore_candidate(backup["backup_name"])
        require(candidate["ok"], f"restore_candidate_failed={candidate}")
        require(candidate["replaces_live_database"] is False, candidate)
        candidate_path = Path(tmp) / "restore_candidates" / candidate["candidate_name"]
        require(candidate_path.is_file(), f"restore_candidate_missing={candidate_path}")
        require(
            store._file_sha256(store.db_path) == live_hash_before,
            "restore_candidate_modified_live_database",
        )
        backup_path = Path(tmp) / "backups" / backup["backup_name"]
        backup_path.write_bytes(backup_path.read_bytes() + b"tampered")
        tampered = store.validate_backup(backup["backup_name"])
        require(not tampered["ok"], f"tampered_backup_accepted={tampered}")
        require(not tampered["manifest_matches"], f"tampered_manifest_accepted={tampered}")
        delete_preview = store.delete_evidence(
            request_id="delete:test:preview",
            actor_id="assistant",
            dry_run=True,
        )
        require(delete_preview["matched"] == 1 and delete_preview["deleted"] == 0, delete_preview)
        deleted = store.delete_evidence(
            request_id="delete:test:confirmed",
            actor_id="assistant",
            dry_run=False,
        )
        require(deleted["deleted"] == 1, deleted)
        replay = store.delete_evidence(
            request_id="delete:test:confirmed",
            actor_id="assistant",
            dry_run=False,
        )
        require(replay["idempotent_replay"] and replay["deleted"] == 1, replay)
        require(store.status()["event_count"] == 1, "confirmed_delete_not_applied")
        require(_like_pattern("%_\\") == "%\\%\\_\\\\%", "like_pattern_escape")


def check_migration_compatibility() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "memory_warehouse.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE warehouse_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL UNIQUE,
                    scope_id TEXT NOT NULL DEFAULT '',
                    unified_msg_origin TEXT NOT NULL DEFAULT '',
                    actor_id TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT 'message',
                    content TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE warehouse_events_fts USING fts5(
                    content, evidence_id UNINDEXED, scope_id UNINDEXED,
                    role UNINDEXED, event_type UNINDEXED, tokenize='unicode61'
                );
                """
            )
        store = MemoryWarehouseStore(tmp, max_content_chars=1000)
        store.initialize()
        with sqlite3.connect(db_path) as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(warehouse_events)")
            }
            for column in (
                "external_event_id",
                "platform",
                "message_type",
                "session_id",
                "group_id",
                "actor_name",
            ):
                require(column in columns, f"migration_column_missing={column}")
            audit_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='warehouse_deletion_audit'"
            ).fetchone()
            require(audit_table is not None, "migration_deletion_audit_missing")
            conn.execute("PRAGMA journal_mode=DELETE")


def report_tracked_cache_pollution() -> None:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tracked = completed.stdout.decode("utf-8", errors="replace").split("\0")
    polluted = sorted(
        path for path in tracked
        if path and ("/__pycache__/" in f"/{path}" or path.endswith(".pyc"))
    )
    print("tracked_cache_pollution=" + json.dumps(polluted, ensure_ascii=False))


def main() -> None:
    check_files()
    check_store()
    check_migration_compatibility()
    report_tracked_cache_pollution()
    print("memory_warehouse_plugin_check=ok")


if __name__ == "__main__":
    main()
