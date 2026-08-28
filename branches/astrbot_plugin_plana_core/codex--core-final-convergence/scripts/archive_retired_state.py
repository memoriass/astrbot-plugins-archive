from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RETIRED_TABLES = (
    "workflow_runs",
    "workflow_events",
    "declarative_workflow_versions",
    "declarative_workflow_heads",
    "capability_candidate_packages",
    "reusable_workflow_candidates",
    "task_records",
    "planner_steps",
)
HERMES_MARKERS = ("hermes", "plana.hermes.", "hermes_delegate")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    cursor = conn.execute(f'SELECT * FROM "{table}"')
    columns = [item[0] for item in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str, sort_keys=True))
            handle.write("\n")
    written = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)
    if written != len(rows):
        raise RuntimeError(f"archive_row_mismatch:{path.name}:{written}:{len(rows)}")
    digest = _hash(path)
    if digest != _hash(path):
        raise RuntimeError(f"archive_hash_mismatch:{path.name}")
    return {"file": path.name, "rows": len(rows), "sha256": digest}


def _hermes_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "remote_task_runs"):
        return []
    matches = []
    for row in _rows(conn, "remote_task_runs"):
        serialized = json.dumps(row, ensure_ascii=False, default=str).casefold()
        if any(marker in serialized for marker in HERMES_MARKERS):
            matches.append(row)
    return matches


def _backup_database(db_path: Path, backup_path: Path) -> None:
    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def archive_database(db_path: Path, archive_root: Path, *, apply: bool) -> dict[str, Any]:
    db_path = db_path.resolve()
    archive_root = archive_root.resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    private_dir = archive_root / "private-data" / "core-db" / timestamp
    manifest_dir = archive_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    if apply:
        private_dir.mkdir(parents=True, exist_ok=False)
        backup = private_dir / db_path.name
        _backup_database(db_path, backup)
    else:
        backup = None

    exports: list[dict[str, Any]] = []
    removed_tables: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        for table in RETIRED_TABLES:
            if not _table_exists(conn, table):
                continue
            rows = _rows(conn, table)
            if apply:
                record = _write_jsonl(private_dir / f"{table}.jsonl", rows)
            else:
                record = {"file": f"{table}.jsonl", "rows": len(rows), "sha256": "dry-run"}
            record["table"] = table
            exports.append(record)

        hermes_rows = _hermes_rows(conn)
        if hermes_rows:
            if apply:
                record = _write_jsonl(private_dir / "remote_task_runs.hermes.jsonl", hermes_rows)
            else:
                record = {"file": "remote_task_runs.hermes.jsonl", "rows": len(hermes_rows), "sha256": "dry-run"}
            record["table"] = "remote_task_runs:hermes_only"
            exports.append(record)

        if apply:
            conn.execute("BEGIN IMMEDIATE")
            for table in RETIRED_TABLES:
                if _table_exists(conn, table):
                    conn.execute(f'DROP TABLE "{table}"')
                    removed_tables.append(table)
            if hermes_rows:
                request_ids = [str(row.get("request_id") or "") for row in hermes_rows]
                conn.executemany(
                    "DELETE FROM remote_task_runs WHERE request_id=?",
                    [(value,) for value in request_ids if value],
                )
            conn.commit()
            remaining_tables = [table for table in RETIRED_TABLES if _table_exists(conn, table)]
            if remaining_tables:
                raise RuntimeError(f"retired_tables_remain:{remaining_tables}")
            if _hermes_rows(conn):
                raise RuntimeError("retired_hermes_rows_remain")
    finally:
        conn.close()

    manifest = {
        "schema": "plana.retired-state-archive.v1",
        "created_at": timestamp,
        "database_name": db_path.name,
        "mode": "apply" if apply else "dry-run",
        "backup": str(backup.relative_to(archive_root)) if backup else "",
        "backup_bytes": backup.stat().st_size if backup else 0,
        "backup_sha256": _hash(backup) if backup else "",
        "exports": exports,
        "removed_tables": removed_tables,
        "removed_hermes_rows": len(hermes_rows) if apply else 0,
    }
    safe_name = "".join(character if character.isalnum() else "-" for character in db_path.stem).strip("-")
    manifest_path = manifest_dir / f"core-db-{safe_name}-{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive and remove retired Plana Core state.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=Path(r"C:\git\_retired_plana_ecosystem"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.db.is_file():
        raise SystemExit(f"database_missing={args.db}")
    result = archive_database(args.db, args.archive_root, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
