"""Audit log for destructive memory operations."""

from __future__ import annotations

from time import time
from typing import Any

from ..db import Database


class AuditLog:
    """Records destructive operations (delete, clean, rebuild) for traceability."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT,
                    detail TEXT,
                    actor TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_action_created
                    ON audit_events(action, created_at DESC);
                """
            )

    def record(
        self,
        action: str,
        target_type: str,
        target_id: str = "",
        detail: str = "",
        actor: str = "system",
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(action, target_type, target_id, detail, actor, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action[:60],
                    target_type[:40],
                    str(target_id)[:80],
                    detail[:500],
                    actor[:40],
                    int(time()),
                ),
            )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, action, target_type, target_id, detail, actor, created_at FROM audit_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [
            {
                "id": row[0],
                "action": row[1],
                "target_type": row[2],
                "target_id": row[3],
                "detail": row[4],
                "actor": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def count(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
