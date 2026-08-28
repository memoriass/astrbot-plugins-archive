"""Feedback queue — collects user feedback signals for memory quality.

Tracks which memories were useful, which new memories should be created,
and which existing memories should be merged. This enables a closed-loop
improvement cycle for memory retrieval quality.
"""

from __future__ import annotations

import json
from time import time
from typing import Any

from ..db import Database


class FeedbackQueue:
    """Collects and processes memory feedback signals."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    processed_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_scope_status
                    ON memory_feedback(scope_id, status, created_at DESC);
                """
            )

    def submit_useful(
        self, scope_id: str, user_id: str, memory_ids: list[int]
    ) -> int | None:
        """Record that certain memories were useful in a retrieval."""
        if not memory_ids:
            return None
        payload = json.dumps({"memory_ids": memory_ids[:20]})
        return self._insert(scope_id, user_id, "useful", payload)

    def submit_not_useful(
        self, scope_id: str, user_id: str, memory_ids: list[int], reason: str = ""
    ) -> int | None:
        """Record that certain memories were not useful."""
        if not memory_ids:
            return None
        payload = json.dumps({"memory_ids": memory_ids[:20], "reason": reason[:200]})
        return self._insert(scope_id, user_id, "not_useful", payload)

    def submit_new_memory(
        self, scope_id: str, user_id: str, content: str, kind: str = ""
    ) -> int | None:
        """Suggest a new memory that should be created."""
        if not content.strip():
            return None
        payload = json.dumps({"content": content[:1000], "kind": kind[:50]})
        return self._insert(scope_id, user_id, "new_memory", payload)

    def submit_merge(
        self,
        scope_id: str,
        user_id: str,
        memory_ids: list[int],
        merged_content: str = "",
    ) -> int | None:
        """Suggest that certain memories should be merged."""
        if len(memory_ids) < 2:
            return None
        payload = json.dumps(
            {
                "memory_ids": memory_ids[:10],
                "merged_content": merged_content[:1000],
            }
        )
        return self._insert(scope_id, user_id, "merge", payload)

    def pending(self, scope_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return pending feedback items."""
        safe_limit = max(1, min(limit, 50))
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT id, scope_id, user_id, kind, payload, status, created_at
                   FROM memory_feedback WHERE scope_id=? AND status='pending'
                   ORDER BY created_at ASC LIMIT ?""",
                (scope_id, safe_limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_processed(self, feedback_id: int) -> bool:
        """Mark a feedback item as processed."""
        now = int(time())
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE memory_feedback SET status='processed', processed_at=? WHERE id=? AND status='pending'",
                (now, feedback_id),
            ).rowcount
        return affected > 0

    def stats(self, scope_id: str) -> dict[str, int]:
        """Return feedback count by kind and status."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT kind, status, COUNT(*) FROM memory_feedback WHERE scope_id=? GROUP BY kind, status",
                (scope_id,),
            ).fetchall()
        result: dict[str, int] = {}
        for row in rows:
            key = f"{row[0]}_{row[1]}"
            result[key] = int(row[2])
        return result

    def cleanup_old(self, max_age_days: int = 60) -> int:
        """Remove processed feedback older than max_age_days."""
        cutoff = int(time()) - max_age_days * 86400
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM memory_feedback WHERE status='processed' AND created_at < ?",
                (cutoff,),
            ).rowcount
        return affected

    def _insert(self, scope_id: str, user_id: str, kind: str, payload: str) -> int:
        now = int(time())
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO memory_feedback(scope_id, user_id, kind, payload, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (scope_id, user_id[:200], kind, payload, now),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        payload_raw = row[4]
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except (json.JSONDecodeError, TypeError):
            payload = {"raw": payload_raw}
        return {
            "id": row[0],
            "scope_id": row[1],
            "user_id": row[2],
            "kind": row[3],
            "payload": payload,
            "status": row[5],
            "created_at": row[6],
        }
