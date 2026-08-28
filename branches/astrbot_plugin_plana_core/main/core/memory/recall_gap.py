"""Recall gap tracker — records failed queries and resolved answers.

Aligned with NachoBot thinking-back not-found retention pattern:
when memory retrieval finds nothing relevant, the query is stored;
when new memories arrive that could answer a stored query, it is marked solved.
"""

from __future__ import annotations

from time import time
from typing import Any

from ..db import Database


class RecallGapTracker:
    """Tracks queries that failed to retrieve relevant memories."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recall_gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    resolved_at INTEGER,
                    resolved_by TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recall_gaps_scope_status
                    ON recall_gaps(scope_id, status, created_at DESC);
                """
            )

    def record_gap(self, scope_id: str, user_id: str, query: str) -> int | None:
        """Record a query that returned no relevant results."""
        if not query.strip():
            return None
        # Avoid duplicate open gaps for the same query in same scope
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM recall_gaps WHERE scope_id=? AND query=? AND status='open' LIMIT 1",
                (scope_id, query[:500]),
            ).fetchone()
            if existing:
                return int(existing[0])
            cursor = conn.execute(
                "INSERT INTO recall_gaps(scope_id, user_id, query, status, created_at) VALUES (?, ?, ?, 'open', ?)",
                (scope_id, user_id, query[:500], int(time())),
            )
            return cursor.lastrowid

    def resolve_gap(self, gap_id: int, resolved_by: str = "new_memory") -> bool:
        """Mark a gap as resolved."""
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE recall_gaps SET status='resolved', resolved_at=?, resolved_by=? WHERE id=? AND status='open'",
                (int(time()), resolved_by[:80], gap_id),
            ).rowcount
        return affected > 0

    def open_gaps(self, scope_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return open (unresolved) gaps for a scope."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, scope_id, user_id, query, status, created_at FROM recall_gaps WHERE scope_id=? AND status='open' ORDER BY created_at DESC LIMIT ?",
                (scope_id, max(1, min(limit, 50))),
            ).fetchall()
        return [
            {
                "id": row[0],
                "scope_id": row[1],
                "user_id": row[2],
                "query": row[3],
                "status": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    def recent_resolved(self, scope_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return recently resolved gaps."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, scope_id, user_id, query, status, resolved_at, resolved_by, created_at FROM recall_gaps WHERE scope_id=? AND status='resolved' ORDER BY resolved_at DESC LIMIT ?",
                (scope_id, max(1, min(limit, 50))),
            ).fetchall()
        return [
            {
                "id": row[0],
                "scope_id": row[1],
                "user_id": row[2],
                "query": row[3],
                "status": row[4],
                "resolved_at": row[5],
                "resolved_by": row[6],
                "created_at": row[7],
            }
            for row in rows
        ]

    def try_resolve_with_content(
        self, scope_id: str, new_content: str, max_check: int = 5
    ) -> list[int]:
        """Check if any open gaps can be resolved by new content keywords."""
        if not new_content.strip():
            return []
        terms = self._extract_terms(new_content)
        if not terms:
            return []
        resolved_ids = []
        gaps = self.open_gaps(scope_id, limit=max_check)
        for gap in gaps:
            gap_terms = self._extract_terms(gap["query"])
            if not gap_terms:
                continue
            overlap = len(set(terms) & set(gap_terms))
            if overlap >= 2 or (len(gap_terms) <= 2 and overlap >= 1):
                if self.resolve_gap(gap["id"], resolved_by="content_match"):
                    resolved_ids.append(gap["id"])
        return resolved_ids

    def stats(self, scope_id: str) -> dict[str, int]:
        """Return gap statistics for a scope."""
        with self.db.connect() as conn:
            open_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM recall_gaps WHERE scope_id=? AND status='open'",
                    (scope_id,),
                ).fetchone()[0]
            )
            resolved_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM recall_gaps WHERE scope_id=? AND status='resolved'",
                    (scope_id,),
                ).fetchone()[0]
            )
        return {"open": open_count, "resolved": resolved_count}

    def _extract_terms(self, text: str) -> list[str]:
        terms = []
        for raw in text.replace("/", " ").replace("_", " ").split():
            term = raw.strip().lower()
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        return terms[:10]
