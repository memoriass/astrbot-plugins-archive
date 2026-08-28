from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_gallery.assets.store import GalleryStore  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_snapshot(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        tables = {str(row[0]) for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assets = int(conn.execute("SELECT COUNT(*) FROM gallery_assets").fetchone()[0])
        tag_relations = int(conn.execute(
            "SELECT COUNT(*) FROM gallery_asset_tags"
        ).fetchone()[0]) if "gallery_asset_tags" in tables else 0
        emotion_profiles = int(conn.execute(
            "SELECT COUNT(*) FROM gallery_asset_emotions"
        ).fetchone()[0]) if "gallery_asset_emotions" in tables else 0
        review_assets = int(conn.execute(
            "SELECT COUNT(DISTINCT asset_id) FROM gallery_asset_tags WHERE tag='needs-review'"
        ).fetchone()[0]) if "gallery_asset_tags" in tables else 0
        schema_row = conn.execute(
            "SELECT value FROM gallery_schema_meta WHERE key='schema_version'"
        ).fetchone() if "gallery_schema_meta" in tables else None
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    return {
        "database": str(database), "sha256": sha256_file(database),
        "assets": assets, "tag_relations": tag_relations,
        "emotion_profiles": emotion_profiles, "review_assets": review_assets,
        "schema_version": int(schema_row[0]) if schema_row else 0,
        "integrity_check": integrity,
    }


def backup_database(database: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=False)
    destination = backup_dir / "gallery.sqlite3"
    with sqlite3.connect(database) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return destination


def write_asset_manifest(database: Path, destination: Path) -> dict[str, int]:
    missing = 0
    rows_written = 0
    with sqlite3.connect(database) as conn, destination.open("w", encoding="utf-8") as handle:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT asset_ref, sha256, file_path FROM gallery_assets ORDER BY id"
        ).fetchall()
        for row in rows:
            path = Path(str(row["file_path"]))
            actual = sha256_file(path) if path.is_file() else ""
            missing += int(not actual)
            handle.write(json.dumps({
                "asset_ref": str(row["asset_ref"]),
                "database_sha256": str(row["sha256"]),
                "actual_sha256": actual,
                "matches": bool(actual and actual == str(row["sha256"])),
            }, ensure_ascii=False) + "\n")
            rows_written += 1
    return {"assets": rows_written, "missing_files": missing}


def create_backup_bundle(
    database: Path, backup_root: Path, dry_run: dict[str, Any]
) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"gallery-tag-governance-{stamp}"
    backup_db = backup_database(database, backup_dir)
    before = database_snapshot(database)
    backup = database_snapshot(backup_db)
    manifest = write_asset_manifest(database, backup_dir / "asset-sha256.jsonl")
    (backup_dir / "migration-dry-run.json").write_text(
        json.dumps(dry_run, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (backup_dir / "backup-summary.json").write_text(
        json.dumps({"source": before, "backup": backup, "manifest": manifest},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if (
        before["assets"] != backup["assets"]
        or before["tag_relations"] != backup["tag_relations"]
        or backup["integrity_check"] != "ok"
    ):
        raise RuntimeError("backup_logical_validation_failed")
    return backup_dir


def build_store(database: Path) -> GalleryStore:
    store = GalleryStore(str(database.parent))
    store.db_path = database
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and govern legacy Gallery tags")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args()

    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"database_not_found={database}")
    store = build_store(database)
    before = database_snapshot(database)
    dry_run = store.govern_legacy_tags(apply=False)
    backup_dir = None
    if args.apply:
        if args.backup_root:
            backup_dir = create_backup_bundle(database, args.backup_root.resolve(), dry_run)
        store.initialize()
        result = store.govern_legacy_tags(apply=True, batch_id=args.batch_id)
    else:
        result = dry_run
    after = database_snapshot(database)
    payload = {
        "ok": True, "mode": "apply" if args.apply else "dry-run",
        "backup_dir": str(backup_dir) if backup_dir else "",
        "before": before, "after": after, "governance": result,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
