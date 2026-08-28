from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time

from .db import Database
from .identity import IdentityStorage
from .memory.graph_storage import ConceptGraphStorage
from .memory.storage import MemoryStorage
from .models import (
    MemoryRecord,
    PlanaState,
    PlannerStep,
    RelationEdge,
    SemanticMemory,
    SessionStream,
    TaskRecord,
    UserIdentity,
)
from .persona import PersonaStorage


class PlanaStorage:
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.identity_storage = IdentityStorage(self.db)
        self.persona_storage = PersonaStorage(self.db)
        self.memory_storage = MemoryStorage(self.db)
        self.concept_graph_storage = ConceptGraphStorage(self.db)

    def initialize(self) -> None:
        self.identity_storage.initialize()
        self.persona_storage.initialize()
        self.memory_storage.initialize()
        self.concept_graph_storage.initialize()

        # Initialize relation/task tables not owned by subpackages
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS relation_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    confidence REAL NOT NULL,
                    evidence TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(source_id, target_id, relation_type)
                );
                CREATE TABLE IF NOT EXISTS task_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS planner_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    step_index INTEGER NOT NULL,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(task_id, step_index)
                );
                """
            )

    def upsert_identity(self, identity: UserIdentity) -> None:
        self.identity_storage.upsert_identity(identity)

    def upsert_session(self, session: SessionStream) -> None:
        self.identity_storage.upsert_session(session)

    def get_state(self, scope_id: str, default_mode: str) -> PlanaState:
        return self.persona_storage.get_state(scope_id, default_mode)

    def set_state(self, scope_id: str, state: PlanaState) -> None:
        self.persona_storage.set_state(scope_id, state)

    # --- episodic / semantic memory: delegated to MemoryStorage ---

    def add_memory(
        self,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
    ) -> None:
        self.memory_storage.add_memory(
            scope, scope_id, kind, content, importance, source
        )

    def search_memories(
        self, scope_id: str, query: str, limit: int
    ) -> list[MemoryRecord]:
        return self.memory_storage.search_memories(scope_id, query, limit)

    def upsert_semantic(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
    ) -> None:
        self.memory_storage.upsert_semantic(
            scope_id, subject, predicate, object_value, confidence, source
        )

    def search_semantics(
        self, scope_id: str, query: str, limit: int
    ) -> list[SemanticMemory]:
        return self.memory_storage.search_semantics(scope_id, query, limit)

    def memory_has_link(self, memory_id: int, target_type: str) -> bool:
        return self.memory_storage.memory_has_link(memory_id, target_type)

    def link_memory(
        self, memory_id: int, target_type: str, target_id: str, weight: float
    ) -> None:
        self.memory_storage.link_memory(memory_id, target_type, target_id, weight)

    def recent_memories(self, scope_id: str, limit: int) -> list[MemoryRecord]:
        return self.memory_storage.recent_memories(scope_id, limit)

    def recent_memories_by_kind(
        self, scope_id: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        return self.memory_storage.recent_memories_by_kind(scope_id, kind, limit)

    def search_memories_by_kind(
        self, scope_id: str, query: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        return self.memory_storage.search_memories_by_kind(scope_id, query, kind, limit)

    def decay_candidates(
        self, scope_id: str, limit: int, min_importance: float
    ) -> list[MemoryRecord]:
        return self.memory_storage.decay_candidates(scope_id, limit, min_importance)

    def memory_decayed_after(self, memory_id: int, since_ts: int) -> bool:
        return self.memory_storage.memory_decayed_after(memory_id, since_ts)

    def update_memory_importance(self, memory_id: int, importance: float) -> None:
        self.memory_storage.update_memory_importance(memory_id, importance)

    def record_memory_decay(
        self, memory_id: int, old_importance: float, new_importance: float, reason: str
    ) -> None:
        self.memory_storage.record_memory_decay(
            memory_id, old_importance, new_importance, reason
        )

    def memory_counts(self, scope_id: str, user_id: str) -> dict[str, int]:
        return self.memory_storage.memory_counts(scope_id, user_id)

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
        self.memory_storage.add_tool_memory(
            task_id, user_id, tool_name, objective, result_summary, success, risk_level
        )

    def upsert_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float,
        confidence: float,
        evidence: str,
    ) -> None:
        now = int(time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO relation_edges VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                    weight=max(relation_edges.weight, excluded.weight),
                    confidence=max(relation_edges.confidence, excluded.confidence),
                    evidence=excluded.evidence,
                    updated_at=excluded.updated_at
                """,
                (
                    source_id,
                    target_id,
                    relation_type,
                    min(max(weight, 0.0), 1.0),
                    min(max(confidence, 0.0), 1.0),
                    evidence[:400],
                    now,
                ),
            )

    def related_edges(self, node_id: str, limit: int) -> list[RelationEdge]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_id, target_id, relation_type, weight, confidence, evidence, updated_at
                FROM relation_edges
                WHERE source_id=? OR target_id=?
                ORDER BY weight DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (node_id, node_id, limit),
            ).fetchall()
        return [RelationEdge(*row) for row in rows]

    def table_counts(self) -> dict[str, int]:
        tables = (
            "identity_profiles",
            "session_streams",
            "persona_states",
            "episodic_memories",
            "tool_memories",
            "semantic_memories",
            "relation_edges",
            "memory_links",
            "memory_decay_events",
            "task_records",
            "planner_steps",
            "concept_nodes",
            "concept_edges",
        )
        with self._connect() as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

    def add_task(
        self,
        scope_id: str,
        owner_id: str,
        objective: str,
        status: str,
        risk_level: str,
    ) -> TaskRecord:
        now = int(time())
        clean_objective = objective[:600]
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_records(scope_id, owner_id, objective, status, risk_level, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_id,
                    owner_id,
                    clean_objective,
                    status,
                    risk_level,
                    now,
                    now,
                ),
            )
            task_id = int(cursor.lastrowid)
        return TaskRecord(
            task_id,
            scope_id,
            owner_id,
            clean_objective,
            status,
            risk_level,
            now,
            now,
        )

    def list_tasks(self, scope_id: str, limit: int) -> list[TaskRecord]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, scope_id, owner_id, objective, status, risk_level, created_at, updated_at
                FROM task_records
                WHERE scope_id=?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (scope_id, limit),
            ).fetchall()
        return [TaskRecord(*row) for row in rows]

    def get_task(self, scope_id: str, task_id: int) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, scope_id, owner_id, objective, status, risk_level, created_at, updated_at
                FROM task_records
                WHERE scope_id=? AND id=?
                LIMIT 1
                """,
                (scope_id, task_id),
            ).fetchone()
        return TaskRecord(*row) if row else None

    def update_task_status(self, scope_id: str, task_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE task_records
                SET status=?, updated_at=?
                WHERE scope_id=? AND id=?
                """,
                (status, int(time()), scope_id, task_id),
            )

    def add_planner_step(
        self,
        task_id: int,
        step_index: int,
        instruction: str,
        status: str,
    ) -> None:
        now = int(time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO planner_steps(task_id, step_index, instruction, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, step_index, instruction[:400], status, now, now),
            )

    def list_planner_steps(self, task_id: int) -> list[PlannerStep]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, task_id, step_index, instruction, status, created_at, updated_at
                FROM planner_steps
                WHERE task_id=?
                ORDER BY step_index ASC
                """,
                (task_id,),
            ).fetchall()
        return [PlannerStep(*row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return self.db.connect()
