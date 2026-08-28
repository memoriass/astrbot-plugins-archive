"""Recall gap tracker records failed queries and resolved answers.

Aligned with a thinking-back not-found retention pattern:
when memory retrieval finds nothing relevant, the query is stored;
when new memories arrive that could answer a stored query, it is marked solved.
"""

from __future__ import annotations

from time import time
from typing import Any

from ..plugin.db import Database


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
                    candidate_feedback_id INTEGER,
                    candidate_at INTEGER,
                    resolved_at INTEGER,
                    resolved_by TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recall_gaps_scope_status
                    ON recall_gaps(scope_id, status, created_at DESC);
                """
            )
            self._ensure_column(conn, "candidate_feedback_id", "INTEGER")
            self._ensure_column(conn, "candidate_at", "INTEGER")

    def record_gap(self, scope_id: str, user_id: str, query: str) -> int | None:
        """Record a query that returned no relevant results."""
        if not query.strip():
            return None
        # Avoid duplicate open gaps for the same query in same scope
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM recall_gaps WHERE scope_id=? AND query=? AND status IN ('open', 'candidate') LIMIT 1",
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
                "UPDATE recall_gaps SET status='resolved', resolved_at=?, resolved_by=? WHERE id=? AND status IN ('open', 'candidate')",
                (int(time()), resolved_by[:80], gap_id),
            ).rowcount
        return affected > 0

    def mark_candidate(self, gap_id: int, feedback_id: int) -> bool:
        """Mark an open gap as having a pending candidate feedback item."""
        with self.db.connect() as conn:
            affected = conn.execute(
                """UPDATE recall_gaps
                   SET status='candidate', candidate_feedback_id=?, candidate_at=?
                   WHERE id=? AND status='open'""",
                (feedback_id, int(time()), gap_id),
            ).rowcount
        return affected > 0

    def resolve_processed_candidates(
        self,
        scope_id: str,
        limit: int = 50,
    ) -> list[int]:
        """Resolve candidate gaps after their feedback item was processed."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT g.id
                   FROM recall_gaps g
                   JOIN memory_feedback f ON f.id=g.candidate_feedback_id
                   WHERE g.scope_id=? AND g.status='candidate'
                     AND f.status='processed'
                   ORDER BY g.candidate_at ASC LIMIT ?""",
                (scope_id, max(1, min(limit, 100))),
            ).fetchall()
        resolved: list[int] = []
        for row in rows:
            gap_id = int(row[0])
            if self.resolve_gap(gap_id, resolved_by="feedback_processed"):
                resolved.append(gap_id)
        return resolved

    def get(self, gap_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT id, scope_id, user_id, query, status,
                          candidate_feedback_id, candidate_at, resolved_at,
                          resolved_by, created_at
                   FROM recall_gaps WHERE id=?""",
                (gap_id,),
            ).fetchone()
        return self._row(row) if row else None

    def gaps(
        self,
        scope_id: str,
        status: str = "open",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return gaps by status for a scope."""
        safe_status = status if status in {"open", "candidate", "resolved"} else "open"
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT id, scope_id, user_id, query, status,
                          candidate_feedback_id, candidate_at, resolved_at,
                          resolved_by, created_at
                   FROM recall_gaps
                   WHERE scope_id=? AND status=?
                   ORDER BY created_at DESC LIMIT ?""",
                (scope_id, safe_status, max(1, min(limit, 50))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def open_gaps(self, scope_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return open (unresolved) gaps for a scope."""
        return self.gaps(scope_id, "open", limit)

    def recent_resolved(self, scope_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return recently resolved gaps."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT id, scope_id, user_id, query, status,
                          candidate_feedback_id, candidate_at, resolved_at,
                          resolved_by, created_at
                   FROM recall_gaps
                   WHERE scope_id=? AND status='resolved'
                   ORDER BY resolved_at DESC LIMIT ?""",
                (scope_id, max(1, min(limit, 50))),
            ).fetchall()
        return [self._row(row) for row in rows]

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
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM recall_gaps WHERE scope_id=? GROUP BY status",
                (scope_id,),
            ).fetchall()
        result = {"open": 0, "candidate": 0, "resolved": 0}
        for row in rows:
            result[str(row[0])] = int(row[1])
        return result

    def active_scope_ids(self, limit: int = 200) -> list[str]:
        """Return scopes that contain recall gaps, newest first."""
        safe_limit = max(1, min(int(limit or 200), 500))
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT scope_id, MAX(created_at) AS last_seen
                   FROM recall_gaps WHERE scope_id<>''
                   GROUP BY scope_id ORDER BY last_seen DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _ensure_column(self, conn: Any, column: str, declaration: str) -> None:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(recall_gaps)")}
        if column not in columns:
            conn.execute(f"ALTER TABLE recall_gaps ADD COLUMN {column} {declaration}")

    def _row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row[0],
            "scope_id": row[1],
            "user_id": row[2],
            "query": row[3],
            "status": row[4],
            "candidate_feedback_id": row[5],
            "candidate_at": row[6],
            "resolved_at": row[7],
            "resolved_by": row[8],
            "created_at": row[9],
        }

    def _extract_terms(self, text: str) -> list[str]:
        terms = []
        for raw in text.replace("/", " ").replace("_", " ").split():
            term = raw.strip().lower()
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        return terms[:10]
