from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from archive_retired_state import RETIRED_TABLES, archive_database


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
PRODUCTION_PATHS = (
    ROOT / "main.py",
    ROOT / "plugin",
    ROOT / "dialogue",
    ROOT / "execution",
    ROOT / "utils",
    ROOT / "web",
)
FORBIDDEN = (
    "SecretaryWorkflowKernel",
    "SecretaryTurnAnalyzer",
    "enable_secretary_workflows",
    "command.run_confirmed",
    "workflow_request",
    "/plana/api/workflows/run",
    "/plana/api/workflows/confirm",
    "/plana/api/workflows/cancel",
    "/plana/api/capability-candidates",
    "hermes_request_id",
    "workflow_candidate",
    "pending_workflow",
    "plana_qbittorrent",
    "qb_plugin",
    '"delegate_version": 2',
    "ExecutionEnvelope",
    "execution_envelope",
    "learning_context",
    "capability_registry",
    "sandbox/workflow",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def production_text() -> str:
    chunks = []
    for path in PRODUCTION_PATHS:
        candidates = [path] if path.is_file() else sorted(path.rglob("*.py")) + sorted(path.rglob("*.js"))
        chunks.extend(candidate.read_text(encoding="utf-8-sig") for candidate in candidates)
    return "\n".join(chunks)


def _new_database_tables() -> set[str]:
    from astrbot_plugin_plana_core.plugin.storage import PlanaStorage

    with tempfile.TemporaryDirectory() as directory:
        storage = PlanaStorage(Path(directory) / "plana.sqlite3")
        storage.initialize()
        with storage.db.connect() as conn:
            return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _archive_fixture() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db_path = root / "plana.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE workflow_runs(id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO workflow_runs(value) VALUES ('legacy')")
            conn.execute("CREATE TABLE remote_task_runs(request_id TEXT PRIMARY KEY, payload TEXT)")
            conn.execute("INSERT INTO remote_task_runs VALUES ('codex-1', '{\"contract\":\"plana.codex.runner.v1\"}')")
            conn.execute("INSERT INTO remote_task_runs VALUES ('old-1', '{\"contract\":\"plana.hermes.runner.v1\"}')")
            conn.commit()
        finally:
            conn.close()
        result = archive_database(db_path, root / "archive", apply=True)
        require(result["removed_tables"] == ["workflow_runs"], "archive_table_removal_failed")
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT request_id FROM remote_task_runs ORDER BY request_id").fetchall()
            require(rows == [("codex-1",)], f"archive_codex_history_changed={rows}")
        finally:
            conn.close()


def main() -> None:
    source = production_text()
    for marker in FORBIDDEN:
        require(marker not in source, f"retired_production_marker={marker}")
    require(not (ROOT / "workflows").exists(), "workflow_package_present")
    require(not (ROOT / "task").exists(), "legacy_task_package_present")
    require(not (ROOT / "capability").exists(), "legacy_capability_registry_present")
    require(not (ROOT / "web" / "execution_audit_payload.py").exists(), "legacy_execution_audit_payload_present")
    routes = (ROOT / "web" / "routes.py").read_text(encoding="utf-8")
    require("/plana/api/remote-tasks" in routes, "codex_task_route_missing")
    require("/plana/api/domains" in routes, "domain_catalog_route_missing")
    tables = _new_database_tables()
    require(not tables.intersection(RETIRED_TABLES), f"retired_tables_created={sorted(tables.intersection(RETIRED_TABLES))}")
    _archive_fixture()
    print("final_convergence_check=ok")


if __name__ == "__main__":
    main()
