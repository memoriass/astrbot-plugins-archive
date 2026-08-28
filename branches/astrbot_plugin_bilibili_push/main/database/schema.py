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
    """
    CREATE TABLE IF NOT EXISTS up_aliases (
        alias TEXT,
        normalized_alias TEXT,
        uid TEXT,
        username TEXT,
        face TEXT,
        target_id TEXT DEFAULT '',
        source TEXT,
        confidence REAL DEFAULT 1.0,
        hit_count INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0,
        updated_at INTEGER DEFAULT 0,
        last_used_at INTEGER DEFAULT 0,
        PRIMARY KEY (normalized_alias, uid, target_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_up_aliases_lookup
    ON up_aliases (normalized_alias, target_id, confidence, updated_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS up_alias_evidence (
        alias TEXT,
        normalized_alias TEXT,
        uid TEXT,
        username TEXT,
        face TEXT,
        target_id TEXT DEFAULT '',
        source TEXT,
        confirm_count INTEGER DEFAULT 1,
        hit_count INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0,
        updated_at INTEGER DEFAULT 0,
        last_used_at INTEGER DEFAULT 0,
        PRIMARY KEY (normalized_alias, uid, target_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_up_alias_evidence_lookup
    ON up_alias_evidence (normalized_alias, uid, target_id, updated_at)
    """,
)


def init_schema(conn) -> None:
    for statement in SCHEMA_SQL:
        conn.execute(statement)
