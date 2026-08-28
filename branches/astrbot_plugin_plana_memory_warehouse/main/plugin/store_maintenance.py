from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import re
import shutil
import sqlite3
import time
from typing import Any
import uuid

from .store_common import CONTRACT_VERSION


class MemoryWarehouseMaintenanceMixin:
    def delete_evidence(
        self,
        *,
        request_id: str,
        evidence_ids: list[str] | None = None,
        scope_id: str = "",
        actor_id: str = "",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", clean_request_id):
            return self._error("invalid_request_id")
        clean_ids = list(
            dict.fromkeys(
                item
                for item in (
                    self._bounded(value, 160) for value in (evidence_ids or [])
                )
                if item
            )
        )[:5000]
        clean_scope = self._bounded(scope_id, 200)
        clean_actor = self._bounded(actor_id, 200)
        if not clean_ids and not clean_scope and not clean_actor:
            return self._error("delete_selector_required")
        selector = {
            "evidence_ids": clean_ids,
            "scope_id": clean_scope,
            "actor_id": clean_actor,
        }
        where: list[str] = []
        params: list[Any] = []
        if clean_ids:
            where.append(f"evidence_id IN ({','.join('?' for _ in clean_ids)})")
            params.extend(clean_ids)
        if clean_scope:
            where.append("scope_id=?")
            params.append(clean_scope)
        if clean_actor:
            where.append("actor_id=?")
            params.append(clean_actor)
        condition = " AND ".join(where)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM warehouse_deletion_audit WHERE request_id=?",
                (clean_request_id,),
            ).fetchone()
            if existing:
                return {
                    "ok": True,
                    "contract_version": CONTRACT_VERSION,
                    "request_id": clean_request_id,
                    "dry_run": False,
                    "matched": int(existing["matched"]),
                    "deleted": int(existing["deleted"]),
                    "idempotent_replay": True,
                }
            rows = conn.execute(
                f"SELECT id FROM warehouse_events WHERE {condition} ORDER BY id LIMIT 5000",
                params,
            ).fetchall()
            row_ids = [int(row["id"]) for row in rows]
            if dry_run:
                return {
                    "ok": True,
                    "contract_version": CONTRACT_VERSION,
                    "request_id": clean_request_id,
                    "dry_run": True,
                    "matched": len(row_ids),
                    "deleted": 0,
                    "idempotent_replay": False,
                }
            if row_ids:
                placeholders = ",".join("?" for _ in row_ids)
                conn.execute(
                    f"DELETE FROM warehouse_events_fts WHERE rowid IN ({placeholders})",
                    row_ids,
                )
                conn.execute(
                    f"DELETE FROM warehouse_events WHERE id IN ({placeholders})",
                    row_ids,
                )
            conn.execute(
                """INSERT INTO warehouse_deletion_audit
                   (request_id, selector_json, matched, deleted, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    clean_request_id,
                    json.dumps(selector, ensure_ascii=False, sort_keys=True),
                    len(row_ids),
                    len(row_ids),
                    int(time.time()),
                ),
            )
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "request_id": clean_request_id,
            "dry_run": False,
            "matched": len(row_ids),
            "deleted": len(row_ids),
            "idempotent_replay": False,
        }

    def create_backup(self) -> dict[str, Any]:
        backup_root = self.root / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
        backup_name = f"warehouse-backup-{backup_id}.sqlite3"
        backup_path = backup_root / backup_name
        temporary_path = backup_root / f".{backup_name}.tmp"
        manifest_path = backup_root / f"{backup_name}.json"
        try:
            with self._connect() as source:
                with closing(sqlite3.connect(temporary_path)) as target:
                    source.backup(target)
            validation = self._validate_database_file(temporary_path)
            if not validation["ok"]:
                return self._error("backup_integrity_failed")
            temporary_path.replace(backup_path)
            digest = self._file_sha256(backup_path)
            manifest = {
                "contract_version": CONTRACT_VERSION,
                "backup_name": backup_name,
                "created_at": int(time.time()),
                "sha256": digest,
                "bytes": backup_path.stat().st_size,
                "event_count": validation["event_count"],
                "fts_count": validation["fts_count"],
                "index_consistent": validation["index_consistent"],
                "integrity_check": validation["integrity_check"],
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return {"ok": True, **manifest}
        finally:
            temporary_path.unlink(missing_ok=True)

    def validate_backup(self, backup_name: str) -> dict[str, Any]:
        backup_path = self._backup_path(backup_name)
        if backup_path is None or not backup_path.is_file():
            return self._error("backup_not_found")
        validation = self._validate_database_file(backup_path)
        manifest_path = backup_path.with_name(f"{backup_path.name}.json")
        manifest = self._read_backup_manifest(manifest_path)
        digest = self._file_sha256(backup_path)
        manifest_matches = bool(manifest) and (
            manifest.get("backup_name") == backup_path.name
            and manifest.get("sha256") == digest
            and int(manifest.get("bytes") or 0) == backup_path.stat().st_size
        )
        return {
            **validation,
            "ok": bool(validation["ok"] and manifest_matches),
            "contract_version": CONTRACT_VERSION,
            "backup_name": backup_path.name,
            "sha256": digest,
            "bytes": backup_path.stat().st_size,
            "manifest_matches": manifest_matches,
        }

    def prepare_restore_candidate(self, backup_name: str) -> dict[str, Any]:
        validation = self.validate_backup(backup_name)
        if not validation.get("ok"):
            return {**validation, "error": "backup_validation_failed"}
        backup_path = self._backup_path(backup_name)
        if backup_path is None:
            return self._error("backup_not_found")
        restore_root = self.root / "restore_candidates"
        restore_root.mkdir(parents=True, exist_ok=True)
        candidate_name = (
            f"memory_warehouse.restore-{int(time.time())}-{uuid.uuid4().hex[:12]}.sqlite3"
        )
        temporary_path = restore_root / f".{candidate_name}.tmp"
        candidate_path = restore_root / candidate_name
        try:
            shutil.copy2(backup_path, temporary_path)
            candidate_validation = self._validate_database_file(temporary_path)
            if not candidate_validation["ok"]:
                return self._error("restore_candidate_integrity_failed")
            if self._file_sha256(temporary_path) != validation["sha256"]:
                return self._error("restore_candidate_hash_mismatch")
            temporary_path.replace(candidate_path)
            return {
                "ok": True,
                "contract_version": CONTRACT_VERSION,
                "backup_name": backup_path.name,
                "candidate_name": candidate_name,
                "sha256": validation["sha256"],
                "bytes": candidate_path.stat().st_size,
                "event_count": candidate_validation["event_count"],
                "fts_count": candidate_validation["fts_count"],
                "replaces_live_database": False,
            }
        finally:
            temporary_path.unlink(missing_ok=True)

    def _backup_path(self, backup_name: str) -> Path | None:
        clean_name = str(backup_name or "").strip()
        if not re.fullmatch(r"warehouse-backup-[0-9]+-[0-9a-f]{12}\.sqlite3", clean_name):
            return None
        backup_root = (self.root / "backups").resolve()
        candidate = (backup_root / clean_name).resolve()
        if candidate.parent != backup_root:
            return None
        return candidate

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _read_backup_manifest(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _validate_database_file(path: Path) -> dict[str, Any]:
        try:
            uri = f"{path.resolve().as_uri()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                event_count = int(
                    conn.execute("SELECT COUNT(*) FROM warehouse_events").fetchone()[0]
                )
                fts_count = int(
                    conn.execute("SELECT COUNT(*) FROM warehouse_events_fts").fetchone()[0]
                )
        except (OSError, sqlite3.Error):
            return {
                "ok": False,
                "integrity_check": "unreadable",
                "event_count": 0,
                "fts_count": 0,
                "index_consistent": False,
            }
        return {
            "ok": integrity == "ok" and event_count == fts_count,
            "integrity_check": integrity,
            "event_count": event_count,
            "fts_count": fts_count,
            "index_consistent": event_count == fts_count,
        }

    def rebuild_index(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM warehouse_events ORDER BY id").fetchall()
            conn.execute("DELETE FROM warehouse_events_fts")
            for row in rows:
                self._replace_fts(
                    conn,
                    row_id=int(row["id"]),
                    content=str(row["content"] or ""),
                    evidence_id=str(row["evidence_id"] or ""),
                    scope_id=str(row["scope_id"] or ""),
                    role=str(row["role"] or ""),
                    event_type=str(row["event_type"] or ""),
                )
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "indexed": len(rows),
        }

    def prune(
        self,
        *,
        before_ts: int,
        limit: int = 1000,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        safe_before = self._safe_int(before_ts, 0, 0, self._now() + 86_400)
        if safe_before <= 0:
            return self._error("invalid_before_ts")
        safe_limit = self._safe_int(limit, 1000, 1, 50_000)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id FROM warehouse_events
                   WHERE created_at < ?
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (safe_before, safe_limit),
            ).fetchall()
            row_ids = [int(row["id"]) for row in rows]
            if not dry_run and row_ids:
                placeholders = ",".join("?" for _ in row_ids)
                conn.execute(
                    f"DELETE FROM warehouse_events_fts WHERE rowid IN ({placeholders})",
                    row_ids,
                )
                conn.execute(
                    f"DELETE FROM warehouse_events WHERE id IN ({placeholders})",
                    row_ids,
                )
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "dry_run": dry_run,
            "matched": len(row_ids),
            "deleted": 0 if dry_run else len(row_ids),
            "before_ts": safe_before,
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            event_count = int(
                conn.execute("SELECT COUNT(*) FROM warehouse_events").fetchone()[0]
            )
            scope_count = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT scope_id) FROM warehouse_events"
                ).fetchone()[0]
            )
            actor_count = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT actor_id) FROM warehouse_events"
                ).fetchone()[0]
            )
            earliest = conn.execute(
                "SELECT MIN(created_at) FROM warehouse_events"
            ).fetchone()[0]
            latest = conn.execute(
                "SELECT MAX(created_at) FROM warehouse_events"
            ).fetchone()[0]
            fts_count = int(
                conn.execute("SELECT COUNT(*) FROM warehouse_events_fts").fetchone()[0]
            )
            event_types = {
                str(row["event_type"] or ""): int(row["count"])
                for row in conn.execute(
                    """SELECT event_type, COUNT(*) AS count
                       FROM warehouse_events
                       GROUP BY event_type
                       ORDER BY count DESC
                       LIMIT 20"""
                ).fetchall()
            }
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "storage": "sqlite",
            "event_count": event_count,
            "scope_count": scope_count,
            "actor_count": actor_count,
            "fts_count": fts_count,
            "index_consistent": event_count == fts_count,
            "earliest_created_at": int(earliest or 0),
            "latest_created_at": int(latest or 0),
            "event_types": event_types,
        }
