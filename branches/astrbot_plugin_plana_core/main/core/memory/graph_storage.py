from __future__ import annotations

from time import time

from ..db import Database
from .models import ConceptEdge, ConceptNode


class ConceptGraphStorage:
    """SQLite storage for concept graph nodes and edges."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS concept_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept TEXT NOT NULL UNIQUE,
                    memory_items TEXT NOT NULL DEFAULT '',
                    weight REAL NOT NULL DEFAULT 1.0,
                    created_at INTEGER NOT NULL,
                    last_modified INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS concept_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    strength INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    last_modified INTEGER NOT NULL,
                    UNIQUE(source, target)
                );
                """
            )

    def get_node(self, concept: str) -> ConceptNode | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, concept, memory_items, weight, created_at, last_modified FROM concept_nodes WHERE concept=? LIMIT 1",
                (concept,),
            ).fetchone()
        return ConceptNode(*row) if row else None

    def save_node(
        self,
        concept: str,
        memory_items: str,
        weight: float,
        created_at: int | None = None,
        last_modified: int | None = None,
    ) -> ConceptNode:
        now = int(time()) if last_modified is None else last_modified
        existing = self.get_node(concept)
        created = existing.created_at if existing else now
        if created_at is not None:
            created = created_at
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO concept_nodes(concept, memory_items, weight, created_at, last_modified)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(concept) DO UPDATE SET
                    memory_items=excluded.memory_items,
                    weight=excluded.weight,
                    last_modified=excluded.last_modified
                """,
                (concept, memory_items[:4000], max(weight, 0.0), created, now),
            )
            row = conn.execute(
                "SELECT id, concept, memory_items, weight, created_at, last_modified FROM concept_nodes WHERE concept=? LIMIT 1",
                (concept,),
            ).fetchone()
        return ConceptNode(*row)

    def get_edge(self, source: str, target: str) -> ConceptEdge | None:
        source, target = self._ordered_pair(source, target)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, source, target, strength, created_at, last_modified FROM concept_edges WHERE source=? AND target=? LIMIT 1",
                (source, target),
            ).fetchone()
        return ConceptEdge(*row) if row else None

    def save_edge(self, source: str, target: str, strength: int) -> ConceptEdge:
        source, target = self._ordered_pair(source, target)
        now = int(time())
        existing = self.get_edge(source, target)
        created = existing.created_at if existing else now
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO concept_edges(source, target, strength, created_at, last_modified)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, target) DO UPDATE SET
                    strength=excluded.strength,
                    last_modified=excluded.last_modified
                """,
                (source, target, max(int(strength), 1), created, now),
            )
            row = conn.execute(
                "SELECT id, source, target, strength, created_at, last_modified FROM concept_edges WHERE source=? AND target=? LIMIT 1",
                (source, target),
            ).fetchone()
        return ConceptEdge(*row)

    def list_edges_for_concept(self, concept: str) -> list[ConceptEdge]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, source, target, strength, created_at, last_modified FROM concept_edges WHERE source=? OR target=? ORDER BY strength DESC, last_modified DESC, id DESC",
                (concept, concept),
            ).fetchall()
        return [ConceptEdge(*row) for row in rows]

    def load_all_nodes(self) -> list[ConceptNode]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, concept, memory_items, weight, created_at, last_modified FROM concept_nodes ORDER BY weight DESC, last_modified DESC, id DESC"
            ).fetchall()
        return [ConceptNode(*row) for row in rows]

    def load_all_edges(self) -> list[ConceptEdge]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, source, target, strength, created_at, last_modified FROM concept_edges ORDER BY strength DESC, last_modified DESC, id DESC"
            ).fetchall()
        return [ConceptEdge(*row) for row in rows]

    def delete_node(self, concept: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM concept_edges WHERE source=? OR target=?",
                (concept, concept),
            )
            conn.execute("DELETE FROM concept_nodes WHERE concept=?", (concept,))

    def delete_edge(self, source: str, target: str) -> None:
        source, target = self._ordered_pair(source, target)
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM concept_edges WHERE source=? AND target=?",
                (source, target),
            )

    def count_nodes(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM concept_nodes").fetchone()[0])

    def count_edges(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0])

    def _ordered_pair(self, source: str, target: str) -> tuple[str, str]:
        return tuple(sorted((source, target)))
