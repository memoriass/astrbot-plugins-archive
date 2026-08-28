from __future__ import annotations

import json
from time import time
from typing import Any

from ..plugin.db import Database


class ProfileEvidenceStorage:
    """Evidence, snapshots, and refresh queue for structured person profiles."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profile_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    predicate TEXT NOT NULL DEFAULT '',
                    object_value TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    source_memory_id INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_profile_evidence_user
                    ON profile_evidence(scope_id, user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS profile_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    semantic_count INTEGER NOT NULL DEFAULT 0,
                    relation_count INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_profile_snapshots_user
                    ON profile_snapshots(scope_id, user_id, created_at DESC);
                """
            )

    def record_evidence(
        self,
        *,
        scope_id: str,
        user_id: str,
        kind: str,
        subject: str = "",
        predicate: str = "",
        object_value: str = "",
        confidence: float = 0.0,
        source: str = "",
        source_memory_id: int = 0,
    ) -> int:
        now = int(time())
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO profile_evidence
                   (scope_id, user_id, kind, subject, predicate, object_value,
                    confidence, source, source_memory_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope_id[:200],
                    user_id[:200],
                    kind[:80],
                    subject[:200],
                    predicate[:80],
                    object_value[:800],
                    max(0.0, min(float(confidence), 1.0)),
                    source[:120],
                    max(0, int(source_memory_id or 0)),
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def snapshot(
        self,
        *,
        scope_id: str,
        user_id: str,
        summary: str,
        profile: dict[str, Any] | None,
        semantic_count: int,
        relation_count: int,
        source: str,
    ) -> int:
        now = int(time())
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO profile_snapshots
                   (scope_id, user_id, summary, profile_json, semantic_count,
                    relation_count, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope_id[:200],
                    user_id[:200],
                    summary[:1200],
                    json.dumps(profile or {}, ensure_ascii=False, default=str)[:4000],
                    max(0, int(semantic_count)),
                    max(0, int(relation_count)),
                    source[:120],
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def recent_evidence(
        self,
        scope_id: str,
        user_id: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        where = ["scope_id=?"]
        params: list[Any] = [scope_id]
        if user_id:
            where.append("user_id=?")
            params.append(user_id)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT id, scope_id, user_id, kind, subject, predicate,
                           object_value, confidence, source, source_memory_id, created_at
                    FROM profile_evidence
                    WHERE {" AND ".join(where)}
                    ORDER BY created_at DESC, id DESC LIMIT ?""",
                (*params, safe_limit),
            ).fetchall()
        return [self._evidence_row(row) for row in rows]

    def recent_snapshots(
        self,
        scope_id: str,
        user_id: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 20))
        where = ["scope_id=?"]
        params: list[Any] = [scope_id]
        if user_id:
            where.append("user_id=?")
            params.append(user_id)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT id, scope_id, user_id, summary, profile_json,
                           semantic_count, relation_count, source, created_at
                    FROM profile_snapshots
                    WHERE {" AND ".join(where)}
                    ORDER BY created_at DESC, id DESC LIMIT ?""",
                (*params, safe_limit),
            ).fetchall()
        return [self._snapshot_row(row) for row in rows]

    def _evidence_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "scope_id": row[1],
            "user_id": row[2],
            "kind": row[3],
            "subject": row[4],
            "predicate": row[5],
            "object_value": row[6],
            "confidence": row[7],
            "source": row[8],
            "source_memory_id": row[9],
            "created_at": row[10],
        }

    def _snapshot_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "scope_id": row[1],
            "user_id": row[2],
            "summary": row[3],
            "profile": self._load_json(row[4]),
            "semantic_count": row[5],
            "relation_count": row[6],
            "source": row[7],
            "created_at": row[8],
        }

    def _load_json(self, value: str) -> dict[str, Any]:
        try:
            data = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
