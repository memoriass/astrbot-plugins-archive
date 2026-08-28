from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .integrity import skill_body_hash
from .models import SkillDraft


class SkillDraftStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    body_hash TEXT NOT NULL DEFAULT '',
                    approved_hash TEXT NOT NULL DEFAULT '',
                    exported_hash TEXT NOT NULL DEFAULT '',
                    source_uri TEXT NOT NULL DEFAULT '',
                    origin_model TEXT NOT NULL DEFAULT '',
                    review_actor TEXT NOT NULL DEFAULT '',
                    scanner_version TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL,
                    scan_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    approved_at INTEGER,
                    exported_at INTEGER,
                    exported_path TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_skill_drafts_status ON skill_drafts(status)"
            )
            self._ensure_column(conn, "body_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "approved_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "exported_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "source_uri", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "origin_model", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "review_actor", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "scanner_version", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "exported_at", "INTEGER")

    def create(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        source: str,
        trust_level: str,
        body: str,
        scan: dict[str, Any],
        body_hash: str = "",
        source_uri: str = "",
        origin_model: str = "",
        scanner_version: str = "",
    ) -> SkillDraft:
        now = int(time.time())
        effective_body_hash = body_hash or skill_body_hash(body)
        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO skill_drafts
                (slug, name, description, status, source, trust_level, body,
                 scan_json, created_at, updated_at, body_hash, source_uri,
                 origin_model, scanner_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    name,
                    description,
                    "quarantined",
                    source,
                    trust_level,
                    body,
                    json.dumps(scan, ensure_ascii=False),
                    now,
                    now,
                    effective_body_hash,
                    source_uri,
                    origin_model,
                    scanner_version,
                ),
            )
            draft_id = int(cur.lastrowid)
        found = self.get(draft_id, include_body=True)
        if found is None:
            raise RuntimeError("created_skill_draft_missing")
        return found

    def get(self, draft_id: int, *, include_body: bool = False) -> SkillDraft | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM skill_drafts WHERE id=?",
                (draft_id,),
            ).fetchone()
        return self._row(row, include_body=include_body) if row else None

    def list(self, *, status: str = "", limit: int = 50) -> list[SkillDraft]:
        bounded_limit = max(1, min(int(limit or 50), 200))
        with self._connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM skill_drafts WHERE status=? ORDER BY id DESC LIMIT ?",
                    (status, bounded_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM skill_drafts ORDER BY id DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
        return [self._row(row, include_body=False) for row in rows]

    def update_status(
        self,
        draft_id: int,
        status: str,
        *,
        exported_path: str = "",
        approved_hash: str = "",
        exported_hash: str = "",
        review_actor: str = "",
        exported_at: int | None = None,
    ) -> SkillDraft | None:
        now = int(time.time())
        approved_at = now if status == "approved" else None
        exported_at_value = (
            int(exported_at)
            if status == "exported" and exported_at is not None
            else (now if status == "exported" else None)
        )
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE skill_drafts
                SET status=?, updated_at=?, approved_at=COALESCE(?, approved_at),
                    exported_at=COALESCE(?, exported_at),
                    exported_path=COALESCE(NULLIF(?, ''), exported_path),
                    approved_hash=COALESCE(NULLIF(?, ''), approved_hash),
                    exported_hash=COALESCE(NULLIF(?, ''), exported_hash),
                    review_actor=COALESCE(NULLIF(?, ''), review_actor)
                WHERE id=?
                """,
                (
                    status,
                    now,
                    approved_at,
                    exported_at_value,
                    exported_path,
                    approved_hash,
                    exported_hash,
                    review_actor,
                    draft_id,
                ),
            )
        return self.get(draft_id, include_body=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _row(self, row: sqlite3.Row, *, include_body: bool) -> SkillDraft:
        raw_body = str(row["body"] or "")
        body = raw_body if include_body else ""
        scan = json.loads(str(row["scan_json"] or "{}"))
        scanner_version = str(row["scanner_version"] or "")
        if not scanner_version and isinstance(scan, dict):
            scanner_version = str(scan.get("scanner_version") or "")
        return SkillDraft(
            id=int(row["id"]),
            slug=str(row["slug"]),
            name=str(row["name"]),
            description=str(row["description"]),
            status=str(row["status"]),  # type: ignore[arg-type]
            source=str(row["source"]),
            trust_level=str(row["trust_level"]),  # type: ignore[arg-type]
            body_hash=str(row["body_hash"] or "") or skill_body_hash(raw_body),
            approved_hash=str(row["approved_hash"] or ""),
            exported_hash=str(row["exported_hash"] or ""),
            source_uri=str(row["source_uri"] or ""),
            origin_model=str(row["origin_model"] or ""),
            review_actor=str(row["review_actor"] or ""),
            scanner_version=scanner_version,
            body=body,
            scan=scan,
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            approved_at=(
                int(row["approved_at"])
                if row["approved_at"] is not None
                else None
            ),
            exported_at=(
                int(row["exported_at"])
                if row["exported_at"] is not None
                else None
            ),
            exported_path=str(row["exported_path"] or ""),
        )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        column: str,
        declaration: str,
    ) -> None:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(skill_drafts)")}
        if column not in columns:
            conn.execute(f"ALTER TABLE skill_drafts ADD COLUMN {column} {declaration}")
