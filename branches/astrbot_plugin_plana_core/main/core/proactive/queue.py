"""Proactive task queue — schedules deferred actions for PlanaCore.

Aligned with NachoBot proactive scheduling pattern:
PlanaCore can enqueue tasks (reminders, follow-ups, reviews, gap-backfill)
that are triggered by a periodic maintain cycle or external scheduler.
PlanaCore does NOT initiate platform-side messages; it only provides
decision payloads that a bridge or host can choose to deliver.
"""

from __future__ import annotations

from time import time
from typing import Any

from ..db import Database

# Task kinds
PROACTIVE_KIND_REMINDER = "reminder"
PROACTIVE_KIND_FOLLOWUP = "followup"
PROACTIVE_KIND_REVIEW = "review"
PROACTIVE_KIND_GAP_BACKFILL = "gap_backfill"
PROACTIVE_KIND_CUSTOM = "custom"

ALL_PROACTIVE_KINDS = (
    PROACTIVE_KIND_REMINDER,
    PROACTIVE_KIND_FOLLOWUP,
    PROACTIVE_KIND_REVIEW,
    PROACTIVE_KIND_GAP_BACKFILL,
    PROACTIVE_KIND_CUSTOM,
)

# Statuses
STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_DELIVERED = "delivered"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"


class ProactiveQueue:
    """Manages deferred proactive tasks with scheduling and delivery tracking."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS proactive_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    scheduled_at INTEGER NOT NULL,
                    expires_at INTEGER,
                    delivered_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_proactive_scope_status
                    ON proactive_tasks(scope_id, status, scheduled_at);
                CREATE INDEX IF NOT EXISTS idx_proactive_ready
                    ON proactive_tasks(status, scheduled_at);
                """
            )

    def enqueue(
        self,
        scope_id: str,
        kind: str,
        payload: str,
        *,
        user_id: str = "",
        priority: int = 0,
        delay_seconds: int = 0,
        ttl_seconds: int | None = None,
    ) -> int | None:
        """Add a proactive task to the queue.

        Args:
            scope_id: Target scope for delivery.
            kind: One of ALL_PROACTIVE_KINDS.
            payload: JSON or text payload describing the action.
            user_id: Optional target user.
            priority: Higher = more urgent.
            delay_seconds: Seconds from now until task becomes ready.
            ttl_seconds: If set, task expires after this many seconds from scheduled_at.
        """
        if kind not in ALL_PROACTIVE_KINDS:
            return None
        now = int(time())
        scheduled_at = now + max(0, delay_seconds)
        expires_at = (scheduled_at + ttl_seconds) if ttl_seconds else None

        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO proactive_tasks
                   (scope_id, user_id, kind, payload, status, priority, scheduled_at, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope_id,
                    user_id[:200],
                    kind,
                    payload[:2000],
                    STATUS_PENDING,
                    priority,
                    scheduled_at,
                    expires_at,
                    now,
                ),
            )
            return cursor.lastrowid

    def poll_ready(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return tasks that are due (scheduled_at <= now, not expired).

        Moves them from pending to ready status atomically.
        """
        now = int(time())
        safe_limit = max(1, min(limit, 20))

        with self.db.connect() as conn:
            # Expire overdue tasks first
            conn.execute(
                "UPDATE proactive_tasks SET status=? WHERE status=? AND expires_at IS NOT NULL AND expires_at < ?",
                (STATUS_EXPIRED, STATUS_PENDING, now),
            )
            # Find due tasks
            rows = conn.execute(
                """SELECT id, scope_id, user_id, kind, payload, priority, scheduled_at, expires_at, created_at
                   FROM proactive_tasks
                   WHERE status=? AND scheduled_at <= ?
                   ORDER BY priority DESC, scheduled_at ASC
                   LIMIT ?""",
                (STATUS_PENDING, now, safe_limit),
            ).fetchall()
            if not rows:
                return []
            # Mark as ready
            ids = [row[0] for row in rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE proactive_tasks SET status=? WHERE id IN ({placeholders})",  # noqa: S608
                [STATUS_READY, *ids],
            )

        return [
            {
                "id": row[0],
                "scope_id": row[1],
                "user_id": row[2],
                "kind": row[3],
                "payload": row[4],
                "priority": row[5],
                "scheduled_at": row[6],
                "expires_at": row[7],
                "created_at": row[8],
            }
            for row in rows
        ]

    def mark_delivered(self, task_id: int) -> bool:
        """Mark a ready task as delivered."""
        now = int(time())
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE proactive_tasks SET status=?, delivered_at=? WHERE id=? AND status=?",
                (STATUS_DELIVERED, now, task_id, STATUS_READY),
            ).rowcount
        return affected > 0

    def cancel(self, task_id: int) -> bool:
        """Cancel a pending or ready task."""
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE proactive_tasks SET status=? WHERE id=? AND status IN (?, ?)",
                (STATUS_CANCELLED, task_id, STATUS_PENDING, STATUS_READY),
            ).rowcount
        return affected > 0

    def pending_count(self, scope_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM proactive_tasks WHERE scope_id=? AND status=?",
                (scope_id, STATUS_PENDING),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_tasks(
        self, scope_id: str, *, status: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """List tasks for a scope, optionally filtered by status."""
        safe_limit = max(1, min(limit, 50))
        with self.db.connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT id, scope_id, user_id, kind, payload, status, priority, scheduled_at, expires_at, delivered_at, created_at
                       FROM proactive_tasks WHERE scope_id=? AND status=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (scope_id, status, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, scope_id, user_id, kind, payload, status, priority, scheduled_at, expires_at, delivered_at, created_at
                       FROM proactive_tasks WHERE scope_id=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (scope_id, safe_limit),
                ).fetchall()
        return [
            {
                "id": row[0],
                "scope_id": row[1],
                "user_id": row[2],
                "kind": row[3],
                "payload": row[4],
                "status": row[5],
                "priority": row[6],
                "scheduled_at": row[7],
                "expires_at": row[8],
                "delivered_at": row[9],
                "created_at": row[10],
            }
            for row in rows
        ]

    def stats(self, scope_id: str) -> dict[str, int]:
        """Return task count by status for a scope."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM proactive_tasks WHERE scope_id=? GROUP BY status",
                (scope_id,),
            ).fetchall()
        return {row[0]: int(row[1]) for row in rows}

    def cleanup_old(self, max_age_days: int = 30) -> int:
        """Remove delivered/expired/cancelled tasks older than max_age_days."""
        cutoff = int(time()) - max_age_days * 86400
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM proactive_tasks WHERE status IN (?, ?, ?) AND created_at < ?",
                (STATUS_DELIVERED, STATUS_EXPIRED, STATUS_CANCELLED, cutoff),
            ).rowcount
        return affected
