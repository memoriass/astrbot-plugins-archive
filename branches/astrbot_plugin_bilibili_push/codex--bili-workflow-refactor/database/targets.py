from __future__ import annotations

import sqlite3
import time

from .models import Target


class TargetStoreMixin:
    def get_targets(self) -> list[Target]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT target_id, channel, title, enabled, created_at, updated_at
                FROM targets
                ORDER BY updated_at DESC, target_id ASC
                """
            )
            return [self._target_from_row(row) for row in cursor]

    def set_target_enabled(self, target_id: str, enabled: bool) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            self._ensure_target(conn, target_id)
            cursor = conn.execute(
                """
                UPDATE targets
                SET enabled = ?, updated_at = ?
                WHERE target_id = ?
                """,
                (1 if enabled else 0, int(time.time()), str(target_id)),
            )
            conn.commit()
            return cursor.rowcount > 0

    def sync_targets_from_subscriptions(self, conn) -> None:
        target_rows = conn.execute(
            """
            SELECT DISTINCT target_id
            FROM subscriptions
            WHERE target_id IS NOT NULL AND target_id != ''
            """
        ).fetchall()
        for (target_id,) in target_rows:
            self._ensure_target(conn, target_id)

    def _ensure_target(self, conn, target_id: str) -> None:
        target_id = str(target_id or "")
        if not target_id:
            return
        now = int(time.time())
        conn.execute(
            """
            INSERT OR IGNORE INTO targets (
                target_id, channel, title, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?)
            """,
            (target_id, channel_from_target(target_id), "", now, now),
        )

    @staticmethod
    def _target_from_row(row) -> Target:
        return Target(
            target_id=row[0],
            channel=row[1],
            title=row[2],
            enabled=bool(row[3]),
            created_at=int(row[4] or 0),
            updated_at=int(row[5] or 0),
        )


def channel_from_target(target_id: str) -> str:
    return str(target_id or "").split(":", 1)[0]
