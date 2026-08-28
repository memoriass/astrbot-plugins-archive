from __future__ import annotations

import sqlite3


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS warehouse_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_id TEXT NOT NULL UNIQUE,
            external_event_id TEXT NOT NULL DEFAULT '',
            scope_id TEXT NOT NULL DEFAULT '',
            unified_msg_origin TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            message_type TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            group_id TEXT NOT NULL DEFAULT '',
            actor_id TEXT NOT NULL DEFAULT '',
            actor_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT 'message',
            content TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS warehouse_events_fts
            USING fts5(
                content,
                evidence_id UNINDEXED,
                scope_id UNINDEXED,
                role UNINDEXED,
                event_type UNINDEXED,
                tokenize='unicode61'
            );
        CREATE TABLE IF NOT EXISTS warehouse_deletion_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            selector_json TEXT NOT NULL,
            matched INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        );
        """
    )
    _migrate(conn)
    _ensure_indexes(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(warehouse_events)").fetchall()
    }
    additions = {
        "external_event_id": "TEXT NOT NULL DEFAULT ''",
        "platform": "TEXT NOT NULL DEFAULT ''",
        "message_type": "TEXT NOT NULL DEFAULT ''",
        "session_id": "TEXT NOT NULL DEFAULT ''",
        "group_id": "TEXT NOT NULL DEFAULT ''",
        "actor_name": "TEXT NOT NULL DEFAULT ''",
    }
    for column, ddl in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE warehouse_events ADD COLUMN {column} {ddl}")


def _ensure_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_warehouse_scope_created
            ON warehouse_events(scope_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_warehouse_origin_created
            ON warehouse_events(unified_msg_origin, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_warehouse_actor_created
            ON warehouse_events(actor_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_warehouse_external_event
            ON warehouse_events(external_event_id);
        CREATE INDEX IF NOT EXISTS idx_warehouse_hash
            ON warehouse_events(content_hash);
        CREATE INDEX IF NOT EXISTS idx_warehouse_event_type_created
            ON warehouse_events(event_type, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_warehouse_deletion_created
            ON warehouse_deletion_audit(created_at DESC);
        """
    )
