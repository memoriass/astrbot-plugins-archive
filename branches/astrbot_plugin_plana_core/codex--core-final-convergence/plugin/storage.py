from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time

from .db import Database
from ..dialogue.message_anchor import MessageAnchorStore
from ..memory.graph_storage import ConceptGraphStorage
from ..memory.storage import MemoryStorage
from .models import (
    MemoryAtomRecord,
    MemoryRecord,
    PlanaState,
    RelationEdge,
    SemanticMemory,
)
from ..persona import PersonaStorage


class PlanaStorage:
    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.persona_storage = PersonaStorage(self.db)
        self.memory_storage = MemoryStorage(self.db)
        self.concept_graph_storage = ConceptGraphStorage(self.db)
        self.message_anchors = MessageAnchorStore(self.db)

    def initialize(self) -> None:
        self.persona_storage.initialize()
        self.memory_storage.initialize()
        self.concept_graph_storage.initialize()
        self.message_anchors.initialize()

        # Initialize relation tables not owned by subpackages.
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS relation_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL DEFAULT 'global',
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    confidence REAL NOT NULL,
                    evidence TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(scope_id, source_id, target_id, relation_type)
                );
                """
            )
            self._ensure_relation_edges_scope(conn)

    def get_state(self, scope_id: str, default_mode: str) -> PlanaState:
        return self.persona_storage.get_state(scope_id, default_mode)

    def ensure_state_mode(
        self,
        scope_id: str,
        mode: str,
        default_mode: str | None = None,
    ) -> tuple[PlanaState, bool]:
        return self.persona_storage.ensure_state_mode(scope_id, mode, default_mode)

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
        *,
        actor_id: str = "",
        subject: str = "",
    ) -> int | None:
        return self.memory_storage.add_memory(
            scope,
            scope_id,
            kind,
            content,
            importance,
            source,
            actor_id=actor_id,
            subject=subject,
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

    def semantic_history(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        return self.memory_storage.semantic_history(
            scope_id,
            subject,
            predicate,
            limit,
        )

    def prune_semantic_history(
        self,
        scope_id: str,
        *,
        retention_days: int = 180,
        max_per_key: int = 50,
    ) -> dict[str, int]:
        return self.memory_storage.prune_semantic_history(
            scope_id,
            retention_days=retention_days,
            max_per_key=max_per_key,
        )

    def memory_has_link(self, memory_id: int, target_type: str) -> bool:
        return self.memory_storage.memory_has_link(memory_id, target_type)

    def link_memory(
        self, memory_id: int, target_type: str, target_id: str, weight: float
    ) -> None:
        self.memory_storage.link_memory(memory_id, target_type, target_id, weight)

    def recent_memories(self, scope_id: str, limit: int) -> list[MemoryRecord]:
        return self.memory_storage.recent_memories(scope_id, limit)

    def active_memory_scopes(
        self,
        limit: int = 20,
        *,
        since_ts: int | None = None,
    ) -> list[str]:
        return self.memory_storage.active_scope_ids(limit, since_ts=since_ts)

    def recent_memories_by_kind(
        self, scope_id: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        return self.memory_storage.recent_memories_by_kind(scope_id, kind, limit)

    def search_memories_by_kind(
        self, scope_id: str, query: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        return self.memory_storage.search_memories_by_kind(scope_id, query, kind, limit)

    def search_memories_by_actor(
        self,
        actor_id: str,
        query: str,
        limit: int,
        *,
        scope_id: str = "",
    ) -> list[MemoryRecord]:
        return self.memory_storage.search_memories_by_actor(
            actor_id,
            query,
            limit,
            scope_id=scope_id,
        )

    def search_atoms(
        self, scope_id: str, query: str, limit: int, atom_type: str = ""
    ) -> list[MemoryAtomRecord]:
        return self.memory_storage.search_atoms(scope_id, query, limit, atom_type)

    def recent_atoms(
        self, scope_id: str, limit: int, atom_type: str = ""
    ) -> list[MemoryAtomRecord]:
        return self.memory_storage.recent_atoms(scope_id, limit, atom_type)

    def reinforce_atom(self, atom_id: int, confidence: float | None = None) -> bool:
        return self.memory_storage.reinforce_atom(atom_id, confidence)

    def expire_stale_atoms(self, scope_id: str | None = None) -> int:
        return self.memory_storage.expire_stale_atoms(scope_id)

    def forget_expired_atoms(
        self, older_than_days: float = 7.0, scope_id: str | None = None
    ) -> int:
        return self.memory_storage.forget_expired_atoms(older_than_days, scope_id)

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
        *,
        scope_id: str = "global",
    ) -> None:
        now = int(time())
        scope = str(scope_id or "global")[:200]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO relation_edges (
                    id, scope_id, source_id, target_id, relation_type,
                    weight, confidence, evidence, updated_at
                ) VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, source_id, target_id, relation_type) DO UPDATE SET
                    weight=max(relation_edges.weight, excluded.weight),
                    confidence=max(relation_edges.confidence, excluded.confidence),
                    evidence=excluded.evidence,
                    updated_at=excluded.updated_at
                """,
                (
                    scope,
                    source_id,
                    target_id,
                    relation_type,
                    min(max(weight, 0.0), 1.0),
                    min(max(confidence, 0.0), 1.0),
                    evidence[:400],
                    now,
                ),
            )

    def related_edges(
        self,
        node_id: str,
        limit: int,
        scope_id: str = "global",
    ) -> list[RelationEdge]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            scope = str(scope_id or "global").strip()[:200]
            rows = conn.execute(
                """
                SELECT id, scope_id, source_id, target_id, relation_type,
                       weight, confidence, evidence, updated_at
                FROM relation_edges
                WHERE scope_id=? AND (source_id=? OR target_id=?)
                ORDER BY weight DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (scope, node_id, node_id, limit),
            ).fetchall()
        return [RelationEdge(*row) for row in rows]

    def _ensure_relation_edges_scope(self, conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(relation_edges)").fetchall()
        }
        if "scope_id" in columns:
            return
        conn.executescript(
            """
            ALTER TABLE relation_edges RENAME TO relation_edges_legacy;
            CREATE TABLE relation_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL DEFAULT 'global',
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(scope_id, source_id, target_id, relation_type)
            );
            INSERT INTO relation_edges (
                id, scope_id, source_id, target_id, relation_type,
                weight, confidence, evidence, updated_at
            )
            SELECT id, 'global', source_id, target_id, relation_type,
                   weight, confidence, evidence, updated_at
            FROM relation_edges_legacy;
            DROP TABLE relation_edges_legacy;
            """
        )

    def table_counts(self) -> dict[str, int]:
        tables = (
            "persona_states",
            "episodic_memories",
            "episodic_memories_fts",
            "memory_atoms",
            "memory_atoms_fts",
            "tool_memories",
            "semantic_memories",
            "semantic_memory_history",
            "relation_edges",
            "memory_links",
            "memory_decay_events",
            "assistant_message_anchors",
            "concept_nodes",
            "concept_edges",
            "audit_events",
            "recall_gaps",
            "proactive_tasks",
            "memory_feedback",
            "scope_aliases",
            "memory_embeddings",
            "person_info",
            "profile_evidence",
            "profile_snapshots",
            "remote_task_runs",
        )
        with self._connect() as conn:
            counts: dict[str, int] = {}
            for table in tables:
                try:
                    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    counts[table] = int(row[0]) if row else 0
                except sqlite3.OperationalError:
                    counts[table] = 0
            return counts

    def _connect(self) -> sqlite3.Connection:
        return self.db.connect()
