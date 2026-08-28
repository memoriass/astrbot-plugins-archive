"""Proactive task queue schedules deferred actions for PlanaCore.

Aligned with a proactive scheduling pattern:
PlanaCore can enqueue tasks (reminders, follow-ups, reviews, gap-backfill)
that are triggered by a periodic maintain cycle or external scheduler.
PlanaCore does NOT initiate platform-side messages; it only provides
decision payloads that a bridge or host can choose to deliver.
"""

from __future__ import annotations

import json
from time import time
from typing import Any

from ..plugin.db import Database

# Task kinds
PROACTIVE_KIND_REMINDER = "reminder"
PROACTIVE_KIND_APPOINTMENT = "appointment"
PROACTIVE_KIND_FOLLOWUP = "followup"
PROACTIVE_KIND_REVIEW = "review"
PROACTIVE_KIND_GAP_BACKFILL = "gap_backfill"
PROACTIVE_KIND_CUSTOM = "custom"

ALL_PROACTIVE_KINDS = (
    PROACTIVE_KIND_REMINDER,
    PROACTIVE_KIND_APPOINTMENT,
    PROACTIVE_KIND_FOLLOWUP,
    PROACTIVE_KIND_REVIEW,
    PROACTIVE_KIND_GAP_BACKFILL,
    PROACTIVE_KIND_CUSTOM,
)

# Statuses
STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_RETRY_PENDING = "retry_pending"
STATUS_FAILED = "failed"
STATUS_DELIVERED = "delivered"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = (STATUS_DELIVERED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED)


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
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    locked_until INTEGER,
                    lane TEXT NOT NULL DEFAULT '',
                    runner_run_id TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_proactive_scope_status
                    ON proactive_tasks(scope_id, status, scheduled_at);
                CREATE INDEX IF NOT EXISTS idx_proactive_due
                    ON proactive_tasks(status, scheduled_at);
                """
            )
            self._ensure_columns(conn)
            conn.execute(
                "UPDATE proactive_tasks SET status=?, locked_until=NULL WHERE status='ready'",
                (STATUS_PENDING,),
            )
            conn.execute("DROP INDEX IF EXISTS idx_proactive_ready")

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
        scheduled_at: int | None = None,
        lane: str = "",
        trigger_reason: str = "",
        trigger_scene: str = "",
        effective_capability_view_hash: str = "",
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
        due_at = max(now, int(scheduled_at)) if scheduled_at else now + max(0, delay_seconds)
        expires_at = (due_at + ttl_seconds) if ttl_seconds else None

        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO proactive_tasks
                   (scope_id, user_id, kind, payload, status, priority,
                    scheduled_at, expires_at, lane, trigger_reason, trigger_scene,
                    effective_capability_view_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope_id,
                    user_id[:200],
                    kind,
                    payload[:8000],
                    STATUS_PENDING,
                    priority,
                    due_at,
                    expires_at,
                    lane[:80],
                    " ".join(str(trigger_reason or "").split())[:300],
                    " ".join(str(trigger_scene or "").split())[:120],
                    str(effective_capability_view_hash or "")[:128],
                    now,
                ),
            )
            return cursor.lastrowid

    def enqueue_reminder(
        self,
        scope_id: str,
        user_id: str,
        message: str,
        *,
        scheduled_at: int | None = None,
        delay_seconds: int = 0,
        title: str = "",
        priority: int = 10,
        ttl_seconds: int | None = 86400,
        appointment: bool = False,
        trigger_reason: str = "reminder",
        trigger_scene: str = "",
        effective_capability_view_hash: str = "",
    ) -> int | None:
        payload = {
            "type": "appointment" if appointment else "reminder",
            "title": title[:120],
            "message": message[:1000],
            "scheduled_at": scheduled_at or int(time()) + max(0, delay_seconds),
        }
        return self.enqueue(
            scope_id,
            PROACTIVE_KIND_APPOINTMENT if appointment else PROACTIVE_KIND_REMINDER,
            json.dumps(payload, ensure_ascii=False),
            user_id=user_id,
            priority=priority,
            delay_seconds=delay_seconds,
            ttl_seconds=ttl_seconds,
            scheduled_at=scheduled_at,
            trigger_reason=trigger_reason,
            trigger_scene=trigger_scene,
            effective_capability_view_hash=effective_capability_view_hash,
        )

    def poll_ready(self, limit: int = 5, *, lease_seconds: int = 60) -> list[dict[str, Any]]:
        """Return tasks that are due (scheduled_at <= now, not expired).

        Leases them from pending/retry_pending to in_flight atomically.
        """
        now = int(time())
        safe_limit = max(1, min(limit, 20))
        lease_until = now + max(5, min(int(lease_seconds or 60), 600))

        with self.db.connect() as conn:
            conn.execute(
                """UPDATE proactive_tasks SET status=?, locked_until=NULL
                   WHERE status IN (?, ?, ?) AND expires_at IS NOT NULL AND expires_at < ?""",
                (STATUS_EXPIRED, STATUS_PENDING, STATUS_RETRY_PENDING, STATUS_IN_FLIGHT, now),
            )
            conn.execute(
                """UPDATE proactive_tasks
                   SET status=?, scheduled_at=?, locked_until=NULL,
                       last_error=CASE WHEN last_error='' THEN ? ELSE last_error END
                   WHERE status=? AND locked_until IS NOT NULL AND locked_until < ?""",
                (
                    STATUS_RETRY_PENDING,
                    now,
                    "delivery lease expired",
                    STATUS_IN_FLIGHT,
                    now,
                ),
            )
            rows = conn.execute(
                """SELECT id, scope_id, user_id, kind, payload, priority, scheduled_at,
                          expires_at, created_at, attempts, last_error, locked_until,
                          lane, runner_run_id, trigger_reason, trigger_scene,
                          effective_capability_view_hash
                   FROM proactive_tasks
                   WHERE status IN (?, ?) AND scheduled_at <= ?
                   ORDER BY priority DESC, scheduled_at ASC
                   LIMIT ?""",
                (STATUS_PENDING, STATUS_RETRY_PENDING, now, safe_limit),
            ).fetchall()
            if not rows:
                return []
            ids = [row[0] for row in rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"""UPDATE proactive_tasks
                    SET status=?, attempts=attempts+1, locked_until=?
                    WHERE id IN ({placeholders})""",  # noqa: S608
                [STATUS_IN_FLIGHT, lease_until, *ids],
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
                "attempts": int(row[9] or 0) + 1,
                "last_error": row[10],
                "locked_until": lease_until,
                "lane": row[12],
                "runner_run_id": row[13],
                "trigger_reason": row[14],
                "trigger_scene": row[15],
                "effective_capability_view_hash": row[16],
            }
            for row in rows
        ]

    def mark_delivered(self, task_id: int, *, runner_run_id: str = "") -> bool:
        """Mark a leased task as delivered."""
        now = int(time())
        with self.db.connect() as conn:
            affected = conn.execute(
                """UPDATE proactive_tasks
                   SET status=?, delivered_at=?, locked_until=NULL,
                       runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                       last_error=''
                   WHERE id=? AND status=?""",
                (
                    STATUS_DELIVERED,
                    now,
                    runner_run_id[:200],
                    task_id,
                    STATUS_IN_FLIGHT,
                ),
            ).rowcount
        return affected > 0

    def mark_failed(
        self,
        task_id: int,
        error: str,
        *,
        retry_delay_seconds: int | None = None,
        runner_run_id: str = "",
        max_attempts: int = 5,
    ) -> bool:
        """Return a leased task to retry_pending or mark it failed."""
        now = int(time())
        clean_error = " ".join(str(error or "delivery_failed").split())[:500]
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT attempts FROM proactive_tasks WHERE id=? AND status IN (?, ?)",
                (task_id, STATUS_IN_FLIGHT, STATUS_RETRY_PENDING),
            ).fetchone()
            if row is None:
                return False
            attempts = int(row[0] or 0)
            if attempts >= max(1, int(max_attempts or 5)):
                status = STATUS_FAILED
                scheduled_at = now
            else:
                status = STATUS_RETRY_PENDING
                delay = retry_delay_seconds
                if delay is None:
                    delay = min(300, max(5, 5 * (2 ** max(0, attempts - 1))))
                scheduled_at = now + max(1, int(delay))
            affected = conn.execute(
                """UPDATE proactive_tasks
                   SET status=?, scheduled_at=?, locked_until=NULL, last_error=?,
                       runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id)
                   WHERE id=?""",
                (status, scheduled_at, clean_error, runner_run_id[:200], task_id),
            ).rowcount
        return affected > 0

    def cancel(self, task_id: int) -> bool:
        """Cancel a non-terminal task."""
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE proactive_tasks SET status=?, locked_until=NULL WHERE id=? AND status NOT IN (?, ?, ?, ?)",
                (
                    STATUS_CANCELLED,
                    task_id,
                    STATUS_DELIVERED,
                    STATUS_EXPIRED,
                    STATUS_CANCELLED,
                    STATUS_FAILED,
                ),
            ).rowcount
        return affected > 0

    def pending_count(self, scope_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM proactive_tasks WHERE scope_id=? AND status IN (?, ?)",
                (scope_id, STATUS_PENDING, STATUS_RETRY_PENDING),
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
                    """SELECT id, scope_id, user_id, kind, payload, status, priority, scheduled_at,
                              expires_at, delivered_at, created_at, attempts, last_error,
                              locked_until, lane, runner_run_id, trigger_reason,
                              trigger_scene, effective_capability_view_hash
                       FROM proactive_tasks WHERE scope_id=? AND status=?
                       ORDER BY created_at DESC LIMIT ?""",
                    (scope_id, status, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, scope_id, user_id, kind, payload, status, priority, scheduled_at,
                              expires_at, delivered_at, created_at, attempts, last_error,
                              locked_until, lane, runner_run_id, trigger_reason,
                              trigger_scene, effective_capability_view_hash
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
                "attempts": row[11],
                "last_error": row[12],
                "locked_until": row[13],
                "lane": row[14],
                "runner_run_id": row[15],
                "trigger_reason": row[16],
                "trigger_scene": row[17],
                "effective_capability_view_hash": row[18],
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
                "DELETE FROM proactive_tasks WHERE status IN (?, ?, ?, ?) AND created_at < ?",
                (STATUS_DELIVERED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED, cutoff),
            ).rowcount
        return affected

    def _ensure_columns(self, conn: Any) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(proactive_tasks)").fetchall()
        }
        additions = {
            "attempts": "ALTER TABLE proactive_tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
            "last_error": "ALTER TABLE proactive_tasks ADD COLUMN last_error TEXT NOT NULL DEFAULT ''",
            "locked_until": "ALTER TABLE proactive_tasks ADD COLUMN locked_until INTEGER",
            "lane": "ALTER TABLE proactive_tasks ADD COLUMN lane TEXT NOT NULL DEFAULT ''",
            "runner_run_id": "ALTER TABLE proactive_tasks ADD COLUMN runner_run_id TEXT NOT NULL DEFAULT ''",
            "trigger_reason": "ALTER TABLE proactive_tasks ADD COLUMN trigger_reason TEXT NOT NULL DEFAULT ''",
            "trigger_scene": "ALTER TABLE proactive_tasks ADD COLUMN trigger_scene TEXT NOT NULL DEFAULT ''",
            "effective_capability_view_hash": "ALTER TABLE proactive_tasks ADD COLUMN effective_capability_view_hash TEXT NOT NULL DEFAULT ''",
        }
        for name, sql in additions.items():
            if name not in columns:
                conn.execute(sql)
