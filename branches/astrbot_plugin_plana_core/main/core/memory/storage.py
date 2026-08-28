from __future__ import annotations

from time import time

from ..db import Database
from .audit import AuditLog
from .models import MemoryRecord, SemanticMemory


class MemoryStorage:
    def __init__(self, db: Database):
        self.db = db
        self.audit = AuditLog(db)

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
                    created_at INTEGER NOT NULL
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

    def add_memory(
        self,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
    ) -> None:
        if not content.strip():
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO episodic_memories(scope, scope_id, kind, content, importance, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope,
                    scope_id,
                    kind,
                    content[:1000],
                    importance,
                    source,
                    int(time()),
                ),
            )

    def search_memories(
        self, scope_id: str, query: str, limit: int
    ) -> list[MemoryRecord]:
        terms = self._terms(query)
        if not terms:
            return self.recent_memories(scope_id, limit)
        rows = []
        with self._connect() as conn:
            for term in terms[:6]:
                rows.extend(
                    conn.execute(
                        "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE scope_id=? AND content LIKE ? ORDER BY importance DESC, created_at DESC, id DESC LIMIT ?",
                        (scope_id, f"%{term}%", limit),
                    ).fetchall()
                )
        return self._dedupe_memories(rows, limit)

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
        now = int(time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memories VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, subject, predicate) DO UPDATE SET
                    object_value=excluded.object_value,
                    confidence=max(semantic_memories.confidence, excluded.confidence),
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    scope_id,
                    subject[:160],
                    predicate[:80],
                    object_value[:600],
                    confidence,
                    source,
                    now,
                ),
            )

    def search_semantics(
        self, scope_id: str, query: str, limit: int
    ) -> list[SemanticMemory]:
        if limit <= 0:
            return []
        terms = self._terms(query)
        rows = []
        with self._connect() as conn:
            if not terms:
                rows = conn.execute(
                    "SELECT id, scope_id, subject, predicate, object_value, confidence, source, updated_at FROM semantic_memories WHERE scope_id=? ORDER BY confidence DESC, updated_at DESC LIMIT ?",
                    (scope_id, limit),
                ).fetchall()
            else:
                for term in terms[:6]:
                    rows.extend(
                        conn.execute(
                            "SELECT id, scope_id, subject, predicate, object_value, confidence, source, updated_at FROM semantic_memories WHERE scope_id=? AND (subject LIKE ? OR object_value LIKE ?) ORDER BY confidence DESC, updated_at DESC LIMIT ?",
                            (scope_id, f"%{term}%", f"%{term}%", limit),
                        ).fetchall()
                    )
        return self._dedupe_semantics(rows, limit)

    def memory_has_link(self, memory_id: int, target_type: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_links WHERE memory_id=? AND target_type=? LIMIT 1",
                (memory_id, target_type),
            ).fetchone()
        return row is not None

    def link_memory(
        self, memory_id: int, target_type: str, target_id: str, weight: float
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO memory_links(memory_id, target_type, target_id, weight, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    memory_id,
                    target_type,
                    target_id,
                    min(max(weight, 0.0), 1.0),
                    int(time()),
                ),
            )

    def recent_memories(self, scope_id: str, limit: int) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE scope_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (scope_id, limit),
            ).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def recent_memories_by_kind(
        self, scope_id: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        if not kind.strip():
            return self.recent_memories(scope_id, limit)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE scope_id=? AND kind=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (scope_id, kind.strip(), limit),
            ).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def search_memories_by_kind(
        self, scope_id: str, query: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        if not kind.strip():
            return self.search_memories(scope_id, query, limit)
        terms = self._terms(query)
        if not terms:
            return self.recent_memories_by_kind(scope_id, kind, limit)
        rows = []
        with self._connect() as conn:
            for term in terms[:6]:
                rows.extend(
                    conn.execute(
                        "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE scope_id=? AND kind=? AND content LIKE ? ORDER BY importance DESC, created_at DESC, id DESC LIMIT ?",
                        (scope_id, kind.strip(), f"%{term}%", limit),
                    ).fetchall()
                )
        return self._dedupe_memories(rows, limit)

    def decay_candidates(
        self, scope_id: str, limit: int, min_importance: float
    ) -> list[MemoryRecord]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE scope_id=? AND importance>? ORDER BY importance ASC, created_at ASC, id ASC LIMIT ?",
                (scope_id, min(max(min_importance, 0.0), 1.0), limit),
            ).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def memory_decayed_after(self, memory_id: int, since_ts: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_decay_events WHERE memory_id=? AND created_at>=? LIMIT 1",
                (memory_id, since_ts),
            ).fetchone()
        return row is not None

    def update_memory_importance(self, memory_id: int, importance: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE episodic_memories SET importance=? WHERE id=?",
                (min(max(importance, 0.0), 1.0), memory_id),
            )

    def record_memory_decay(
        self,
        memory_id: int,
        old_importance: float,
        new_importance: float,
        reason: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memory_decay_events(memory_id, old_importance, new_importance, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    memory_id,
                    min(max(old_importance, 0.0), 1.0),
                    min(max(new_importance, 0.0), 1.0),
                    reason[:160],
                    int(time()),
                ),
            )

    def memory_counts(self, scope_id: str, user_id: str) -> dict[str, int]:
        with self._connect() as conn:
            episodic = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE scope_id=?",
                (scope_id,),
            ).fetchone()[0]
            semantic = conn.execute(
                "SELECT COUNT(*) FROM semantic_memories WHERE scope_id=?",
                (scope_id,),
            ).fetchone()[0]
            tool_user = conn.execute(
                "SELECT COUNT(*) FROM tool_memories WHERE user_id=?",
                (user_id,),
            ).fetchone()[0]
            decay_events = conn.execute(
                "SELECT COUNT(*) FROM memory_decay_events e JOIN episodic_memories m ON m.id=e.memory_id WHERE m.scope_id=?",
                (scope_id,),
            ).fetchone()[0]
        return {
            "episodic": int(episodic),
            "semantic": int(semantic),
            "tool_user": int(tool_user),
            "decay_events": int(decay_events),
        }

    def add_tool_memory(
        self,
        task_id: int,
        user_id: str,
        tool_name: str,
        objective: str,
        result_summary: str,
        success: bool,
        risk_level: str,
    ) -> None:
        if not objective.strip() and not result_summary.strip():
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tool_memories(task_id, user_id, tool_name, objective, result_summary, success, risk_level, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(task_id),
                    user_id,
                    tool_name[:80],
                    objective[:600],
                    result_summary[:600],
                    1 if success else 0,
                    risk_level,
                    int(time()),
                ),
            )

    def _dedupe_memories(self, rows: list[tuple], limit: int) -> list[MemoryRecord]:
        seen = set()
        records = []
        for row in rows:
            if row[0] in seen:
                continue
            seen.add(row[0])
            records.append(MemoryRecord(*row))
            if len(records) >= limit:
                break
        return records

    def _dedupe_semantics(self, rows: list[tuple], limit: int) -> list[SemanticMemory]:
        seen = set()
        records = []
        for row in rows:
            if row[0] in seen:
                continue
            seen.add(row[0])
            records.append(SemanticMemory(*row))
            if len(records) >= limit:
                break
        return records

    def _terms(self, query: str) -> list[str]:
        terms = []
        for raw in query.replace("/", " ").replace("_", " ").split():
            term = raw.strip().lower()
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        return terms

    # -- Destructive operations with transaction protection + audit --

    def delete_memory(self, memory_id: int, actor: str = "web") -> dict[str, object]:
        """Delete an episodic memory by ID with cascading link/decay cleanup."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, scope, scope_id, kind, content, importance, source, created_at FROM episodic_memories WHERE id=?",
                (memory_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found", "id": memory_id}
            record = MemoryRecord(*row)
            conn.execute("DELETE FROM memory_links WHERE memory_id=?", (memory_id,))
            conn.execute(
                "DELETE FROM memory_decay_events WHERE memory_id=?", (memory_id,)
            )
            conn.execute("DELETE FROM episodic_memories WHERE id=?", (memory_id,))
        self.audit.record(
            "delete_memory",
            "episodic_memories",
            str(memory_id),
            f"kind={record.kind} content={record.content[:80]}",
            actor,
        )
        return {"ok": True, "id": memory_id, "kind": record.kind}

    def delete_semantic(
        self, semantic_id: int, actor: str = "web"
    ) -> dict[str, object]:
        """Delete a semantic memory by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, scope_id, subject, predicate, object_value, confidence, source, updated_at FROM semantic_memories WHERE id=?",
                (semantic_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found", "id": semantic_id}
            record = SemanticMemory(*row)
            conn.execute("DELETE FROM semantic_memories WHERE id=?", (semantic_id,))
        self.audit.record(
            "delete_semantic",
            "semantic_memories",
            str(semantic_id),
            f"subject={record.subject} predicate={record.predicate}",
            actor,
        )
        return {"ok": True, "id": semantic_id, "subject": record.subject}
