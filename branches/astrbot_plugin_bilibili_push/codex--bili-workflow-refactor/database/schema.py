from __future__ import annotations


SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        uid TEXT,
        username TEXT,
        sub_type TEXT,
        target_id TEXT,
        categories TEXT,
        tags TEXT,
        enabled INTEGER DEFAULT 1,
        PRIMARY KEY (uid, sub_type, target_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        uid TEXT PRIMARY KEY,
        name TEXT,
        face TEXT,
        cookies TEXT,
        valid INTEGER DEFAULT 1,
        status_code INTEGER,
        cooldown_until INTEGER DEFAULT 0,
        failure_count INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0,
        updated_at INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS targets (
        target_id TEXT PRIMARY KEY,
        channel TEXT,
        title TEXT,
        enabled INTEGER DEFAULT 1,
        created_at INTEGER DEFAULT 0,
        updated_at INTEGER DEFAULT 0
    )
    """,
)


def init_schema(conn) -> None:
    for statement in SCHEMA_SQL:
        conn.execute(statement)
