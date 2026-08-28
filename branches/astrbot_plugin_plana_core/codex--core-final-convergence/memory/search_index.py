from __future__ import annotations

import sqlite3


class EpisodicFTSIndex:
    """Optional FTS5 helper for episodic memory keyword search."""

    def __init__(self) -> None:
        self.available = True

    def initialize(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS episodic_memories_fts
                USING fts5(
                    content,
                    memory_id UNINDEXED,
                    scope_id UNINDEXED,
                    kind UNINDEXED,
                    tokenize='unicode61'
                )
                """
            )
            self.sync(conn)
        except sqlite3.Error:
            self.available = False

    def search(
        self,
        conn: sqlite3.Connection,
        scope_id: str,
        terms: list[str],
        limit: int,
        kind: str = "",
    ) -> list[sqlite3.Row]:
        if not self.available:
            return []
        fts_query = self._fts_query(terms[:8])
        if not fts_query:
            return []
        filters = ["m.scope_id=?"]
        params: list[object] = [fts_query, scope_id]
        if kind:
            filters.append("m.kind=?")
            params.append(kind)
        try:
            return conn.execute(
                f"""
                SELECT m.id, m.scope, m.scope_id, m.kind, m.content,
                       m.importance, m.source, m.created_at,
                       m.actor_id, m.subject
                FROM episodic_memories_fts
                JOIN episodic_memories m ON m.id = episodic_memories_fts.memory_id
                WHERE episodic_memories_fts MATCH ?
                  AND {" AND ".join(filters)}
                ORDER BY bm25(episodic_memories_fts) ASC,
                         m.importance DESC,
                         m.created_at DESC,
                         m.id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        except sqlite3.Error:
            return []

    def insert(
        self,
        conn: sqlite3.Connection,
        memory_id: int,
        scope_id: str,
        kind: str,
        content: str,
    ) -> None:
        if not self.available:
            return
        try:
            conn.execute(
                """
                INSERT INTO episodic_memories_fts(rowid, memory_id, scope_id, kind, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memory_id, memory_id, scope_id, kind, content),
            )
        except sqlite3.Error:
            self.available = False

    def delete(self, conn: sqlite3.Connection, memory_id: int) -> None:
        if not self.available:
            return
        try:
            conn.execute(
                "DELETE FROM episodic_memories_fts WHERE memory_id=?",
                (memory_id,),
            )
        except sqlite3.Error:
            self.available = False

    def sync(self, conn: sqlite3.Connection) -> None:
        if not self.available:
            return
        conn.execute(
            """
            DELETE FROM episodic_memories_fts
            WHERE memory_id NOT IN (SELECT id FROM episodic_memories)
            """
        )
        conn.execute(
            """
            INSERT INTO episodic_memories_fts(rowid, memory_id, scope_id, kind, content)
            SELECT id, id, scope_id, kind, content
            FROM episodic_memories
            WHERE id NOT IN (SELECT memory_id FROM episodic_memories_fts)
            """
        )

    def _fts_query(self, terms: list[str]) -> str:
        tokens = []
        for term in terms:
            token = term.strip().replace('"', '""')
            if token:
                tokens.append(f'"{token}"')
        return " OR ".join(tokens)


class MemoryAtomFTSIndex:
    """Optional FTS5 helper for fine-grained memory atoms."""

    def __init__(self) -> None:
        self.available = True

    def initialize(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_atoms_fts
                USING fts5(
                    content,
                    atom_id UNINDEXED,
                    scope_id UNINDEXED,
                    atom_type UNINDEXED,
                    tokenize='unicode61'
                )
                """
            )
            self.sync(conn)
        except sqlite3.Error:
            self.available = False

    def search(
        self,
        conn: sqlite3.Connection,
        scope_id: str,
        terms: list[str],
        limit: int,
        atom_type: str = "",
    ) -> list[sqlite3.Row]:
        if not self.available:
            return []
        fts_query = self._fts_query(terms[:8])
        if not fts_query:
            return []
        filters = ["a.scope_id=?", "a.status='active'"]
        params: list[object] = [fts_query, scope_id]
        if atom_type:
            filters.append("a.atom_type=?")
            params.append(atom_type)
        try:
            return conn.execute(
                f"""
                SELECT a.id, a.parent_memory_id, a.scope, a.scope_id, a.atom_type,
                       a.content, a.importance, a.confidence, a.source,
                       a.created_at, a.last_accessed_at, a.last_reinforced_at,
                       a.ttl_days, a.expires_at, a.status, a.reinforcement_count,
                       a.decay_type, a.metadata
                FROM memory_atoms_fts
                JOIN memory_atoms a ON a.id = memory_atoms_fts.atom_id
                WHERE memory_atoms_fts MATCH ?
                  AND {" AND ".join(filters)}
                ORDER BY bm25(memory_atoms_fts) ASC,
                         a.importance DESC,
                         a.created_at DESC,
                         a.id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        except sqlite3.Error:
            return []

    def insert(
        self,
        conn: sqlite3.Connection,
        atom_id: int,
        scope_id: str,
        atom_type: str,
        content: str,
    ) -> None:
        if not self.available:
            return
        try:
            conn.execute(
                """
                INSERT INTO memory_atoms_fts(rowid, atom_id, scope_id, atom_type, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (atom_id, atom_id, scope_id, atom_type, content),
            )
        except sqlite3.Error:
            self.available = False

    def delete(self, conn: sqlite3.Connection, atom_id: int) -> None:
        if not self.available:
            return
        try:
            conn.execute("DELETE FROM memory_atoms_fts WHERE atom_id=?", (atom_id,))
        except sqlite3.Error:
            self.available = False

    def sync(self, conn: sqlite3.Connection) -> None:
        if not self.available:
            return
        conn.execute(
            """
            DELETE FROM memory_atoms_fts
            WHERE atom_id NOT IN (SELECT id FROM memory_atoms)
            """
        )
        conn.execute(
            """
            DELETE FROM memory_atoms_fts
            WHERE atom_id IN (
                SELECT id FROM memory_atoms WHERE status='forgotten'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memory_atoms_fts(rowid, atom_id, scope_id, atom_type, content)
            SELECT id, id, scope_id, atom_type, content
            FROM memory_atoms
            WHERE status!='forgotten'
              AND id NOT IN (SELECT atom_id FROM memory_atoms_fts)
            """
        )

    def _fts_query(self, terms: list[str]) -> str:
        tokens = []
        for term in terms:
            token = term.strip().replace('"', '""')
            if token:
                tokens.append(f'"{token}"')
        return " OR ".join(tokens)
