from __future__ import annotations

import sqlite3
from typing import Any


class AssetCollectionMixin:
    def initialize_chat_collection(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_chat_collection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_hash TEXT NOT NULL,
                sender_hash TEXT NOT NULL DEFAULT '',
                message_hash TEXT NOT NULL DEFAULT '',
                asset_ref TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                observed_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_collection_scope_time
                ON gallery_chat_collection_events(scope_hash, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_gallery_collection_outcome_time
                ON gallery_chat_collection_events(outcome, observed_at DESC);
            """
        )

    def chat_collection_counts(self, *, scope_hash: str, since: int) -> dict[str, int]:
        with self._connect() as conn:
            scope_count = conn.execute(
                """SELECT COUNT(*) FROM gallery_chat_collection_events
                   WHERE scope_hash=? AND outcome='collected' AND observed_at>=?""",
                (scope_hash, since),
            ).fetchone()[0]
            global_count = conn.execute(
                """SELECT COUNT(*) FROM gallery_chat_collection_events
                   WHERE outcome='collected' AND observed_at>=?""",
                (since,),
            ).fetchone()[0]
        return {"scope": int(scope_count), "global": int(global_count)}

    def chat_collection_hash_status(self, sha256: str) -> dict[str, Any]:
        with self._connect() as conn:
            asset = conn.execute(
                "SELECT * FROM gallery_assets WHERE sha256=?",
                (sha256,),
            ).fetchone()
            if asset:
                return {"status": "existing", "asset": self._row_to_asset(asset)}
            tombstone = conn.execute(
                "SELECT asset_ref FROM gallery_asset_tombstones WHERE sha256=?",
                (sha256,),
            ).fetchone()
        if tombstone:
            return {"status": "tombstoned", "asset_ref": str(tombstone["asset_ref"])}
        return {"status": "new"}

    def record_chat_collection(
        self,
        *,
        scope_hash: str,
        sender_hash: str,
        message_hash: str,
        outcome: str,
        asset_ref: str = "",
        reason: str = "",
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO gallery_chat_collection_events
                   (scope_hash, sender_hash, message_hash, asset_ref, outcome, reason, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope_hash[:64],
                    sender_hash[:64],
                    message_hash[:64],
                    asset_ref[:120],
                    outcome[:32],
                    reason[:160],
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM gallery_chat_collection_events WHERE observed_at<?",
                (now - 30 * 86400,),
            )

    def chat_collection_status(self) -> dict[str, Any]:
        since = self._now() - 86400
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT outcome, COUNT(*) AS count
                   FROM gallery_chat_collection_events WHERE observed_at>=?
                   GROUP BY outcome ORDER BY outcome""",
                (since,),
            ).fetchall()
        return {str(row["outcome"]): int(row["count"]) for row in rows}
