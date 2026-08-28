from __future__ import annotations

from time import time

from ..plugin.db import Database
from .atoms import MemoryAtomStore
from .audit import AuditLog
from .migrations import migrate_legacy_bridge_handoff
from .search_index import EpisodicFTSIndex
from .storage_operations import MemoryStorageOperationsMixin
from .storage_query import MemoryStorageQueryMixin


class MemoryStorage(MemoryStorageOperationsMixin, MemoryStorageQueryMixin):
    def __init__(self, db: Database):
        self.db = db
        self.audit = AuditLog(db)
        self.fts = EpisodicFTSIndex()
        self.atoms = MemoryAtomStore(db)

    def _connect(self):
        return self.db.connect()

    def initialize(self) -> None:
        self.audit.initialize()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    actor_id TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS tool_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    user_id TEXT,
                    tool_name TEXT,
                    objective TEXT,
                    result_summary TEXT,
                    success INTEGER,
                    risk_level TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS semantic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(scope_id, subject, predicate)
                );
                CREATE TABLE IF NOT EXISTS semantic_memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    replacement_value TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_history_key
                ON semantic_memory_history(scope_id, subject, predicate, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_semantic_history_scope_created
                ON semantic_memory_history(scope_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS memory_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(memory_id, target_type, target_id)
                );
                CREATE TABLE IF NOT EXISTS memory_decay_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER NOT NULL,
                    old_importance REAL NOT NULL,
                    new_importance REAL NOT NULL,
                    reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            self.fts.initialize(conn)
            self.atoms.initialize(conn)
            self._ensure_actor_columns(conn)
            self._migrate_legacy_bridge_handoff(conn)

    def _migrate_legacy_bridge_handoff(self, conn) -> None:
        migrate_legacy_bridge_handoff(conn)

    def _ensure_actor_columns(self, conn) -> None:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(episodic_memories)").fetchall()
        }
        if "actor_id" not in columns:
            conn.execute(
                "ALTER TABLE episodic_memories ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''"
            )
        if "subject" not in columns:
            conn.execute(
                "ALTER TABLE episodic_memories ADD COLUMN subject TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodic_actor ON episodic_memories(actor_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodic_subject ON episodic_memories(subject, created_at DESC)"
        )

    def add_memory(
        self,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
        *,
        actor_id: str = "",
        subject: str = "",
    ) -> int | None:
        if not content.strip():
            return None
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO episodic_memories(
                    scope, scope_id, kind, content, importance, source,
                    created_at, actor_id, subject
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope,
                    scope_id,
                    kind,
                    content[:1000],
                    importance,
                    source,
                    int(time()),
                    str(actor_id or "")[:200],
                    str(subject or "")[:200],
                ),
            )
            memory_id = int(cursor.lastrowid)
            self.fts.insert(conn, memory_id, scope_id, kind, content[:1000])
            self.atoms.create_from_memory(
                conn,
                memory_id,
                scope,
                scope_id,
                kind,
                content[:1000],
                importance,
                source,
            )
            return memory_id

    def upsert_semantic(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
    ) -> None:
        if not subject.strip() or not object_value.strip():
            return
        clean_subject = subject[:160]
        clean_predicate = predicate[:80]
        clean_value = object_value[:600]
        clean_source = source[:80]
        clean_confidence = max(0.0, min(float(confidence), 1.0))
        now = int(time())
        with self._connect() as conn:
            current = conn.execute(
                """
                SELECT object_value, confidence, source
                FROM semantic_memories
                WHERE scope_id=? AND subject=? AND predicate=?
                LIMIT 1
                """,
                (scope_id, clean_subject, clean_predicate),
            ).fetchone()
            if current is None:
                conn.execute(
                    """
                    INSERT INTO semantic_memories VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scope_id,
                        clean_subject,
                        clean_predicate,
                        clean_value,
                        clean_confidence,
                        clean_source,
                        now,
                    ),
                )
                self._append_semantic_history(
                    conn,
                    scope_id,
                    clean_subject,
                    clean_predicate,
                    clean_value,
                    clean_confidence,
                    clean_source,
                    "activated",
                    "",
                    now,
                )
                return
            current_value = str(current[0] or "")
            if current_value == clean_value:
                reinforced_confidence = max(float(current[1] or 0.0), clean_confidence)
                conn.execute(
                    """
                    UPDATE semantic_memories
                    SET confidence=?, source=?, updated_at=?
                    WHERE scope_id=? AND subject=? AND predicate=?
                    """,
                    (
                        reinforced_confidence,
                        clean_source,
                        now,
                        scope_id,
                        clean_subject,
                        clean_predicate,
                    ),
                )
                self._append_semantic_history(
                    conn,
                    scope_id,
                    clean_subject,
                    clean_predicate,
                    clean_value,
                    reinforced_confidence,
                    clean_source,
                    "reinforced",
                    "",
                    now,
                )
                return
            self._append_semantic_history(
                conn,
                scope_id,
                clean_subject,
                clean_predicate,
                current_value,
                float(current[1] or 0.0),
                str(current[2] or ""),
                "superseded",
                clean_value,
                now,
            )
            conn.execute(
                """
                UPDATE semantic_memories
                SET object_value=?, confidence=?, source=?, updated_at=?
                WHERE scope_id=? AND subject=? AND predicate=?
                """,
                (
                    clean_value,
                    clean_confidence,
                    clean_source,
                    now,
                    scope_id,
                    clean_subject,
                    clean_predicate,
                ),
            )
            self._append_semantic_history(
                conn,
                scope_id,
                clean_subject,
                clean_predicate,
                clean_value,
                clean_confidence,
                clean_source,
                "activated",
                "",
                now,
            )
