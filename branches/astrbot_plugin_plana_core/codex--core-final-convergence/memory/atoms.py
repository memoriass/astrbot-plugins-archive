from __future__ import annotations

import json
import sqlite3
from time import time
from typing import Any

from ..plugin.db import Database
from .atom_policy import (
    atom_final_score,
    atom_temporal_score,
    atom_texts,
    compute_atom_ttl,
    default_confidence,
    infer_atom_type,
)
from .models import (
    MEMORY_ATOM_STATUS_ACTIVE,
    MEMORY_ATOM_STATUS_EXPIRED,
    MEMORY_ATOM_STATUS_FORGOTTEN,
    MemoryAtomRecord,
)
from .search_index import MemoryAtomFTSIndex


class MemoryAtomStore:
    """Fine-grained memory atoms with LivingMemory-style lifecycle controls."""

    _SELECT_COLUMNS = """
        id, parent_memory_id, scope, scope_id, atom_type, content, importance,
        confidence, source, created_at, last_accessed_at, last_reinforced_at,
        ttl_days, expires_at, status, reinforcement_count, decay_type, metadata
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.fts = MemoryAtomFTSIndex()

    def initialize(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_atoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_memory_id INTEGER NOT NULL,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                atom_type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed_at INTEGER NOT NULL,
                last_reinforced_at INTEGER,
                ttl_days REAL NOT NULL,
                expires_at INTEGER NOT NULL,
                status TEXT NOT NULL,
                reinforcement_count INTEGER NOT NULL,
                decay_type TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(parent_memory_id) REFERENCES episodic_memories(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_memory_atoms_parent
                ON memory_atoms(parent_memory_id);
            CREATE INDEX IF NOT EXISTS idx_memory_atoms_scope_status
                ON memory_atoms(scope_id, status, expires_at);
            CREATE INDEX IF NOT EXISTS idx_memory_atoms_scope_type
                ON memory_atoms(scope_id, atom_type, status);
            CREATE INDEX IF NOT EXISTS idx_memory_atoms_expires
                ON memory_atoms(status, expires_at);
            """
        )
        self.fts.initialize(conn)

    def create_from_memory(
        self,
        conn: sqlite3.Connection,
        memory_id: int,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
    ) -> list[int]:
        atom_ids: list[int] = []
        atom_type = infer_atom_type(kind)
        for atom_text in atom_texts(content):
            atom_ids.append(
                self._insert(
                    conn,
                    parent_memory_id=memory_id,
                    scope=scope,
                    scope_id=scope_id,
                    atom_type=atom_type,
                    content=atom_text,
                    importance=importance,
                    confidence=default_confidence(kind, importance),
                    source=source,
                    metadata={"kind": kind, "source_memory_kind": kind},
                )
            )
        return atom_ids

    def atoms_for_memory(self, parent_memory_id: int) -> list[MemoryAtomRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {self._SELECT_COLUMNS}
                FROM memory_atoms
                WHERE parent_memory_id=?
                ORDER BY id ASC
                """,
                (parent_memory_id,),
            ).fetchall()
        return [MemoryAtomRecord(*row) for row in rows]

    def search(
        self,
        scope_id: str,
        query: str,
        limit: int,
        atom_type: str = "",
    ) -> list[MemoryAtomRecord]:
        if limit <= 0:
            return []
        terms = self._terms(query)
        if not terms:
            return self.recent(scope_id, limit, atom_type)
        with self.db.connect() as conn:
            candidate_limit = max(limit * 2, limit + 4)
            rows = self.fts.search(conn, scope_id, terms, candidate_limit, atom_type)
            rows.extend(
                self._search_like(conn, scope_id, terms, candidate_limit, atom_type)
            )
        records = self._dedupe(rows, candidate_limit)
        records.sort(key=self._rank_score, reverse=True)
        return records[:limit]

    def recent(
        self, scope_id: str, limit: int, atom_type: str = ""
    ) -> list[MemoryAtomRecord]:
        filters = ["scope_id=?", "status='active'"]
        params: list[object] = [scope_id]
        if atom_type:
            filters.append("atom_type=?")
            params.append(atom_type)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {self._SELECT_COLUMNS}
                FROM memory_atoms
                WHERE {" AND ".join(filters)}
                ORDER BY importance DESC, created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        return [MemoryAtomRecord(*row) for row in rows]

    def touch(self, atom_id: int) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE memory_atoms SET last_accessed_at=? WHERE id=?",
                (int(time()), atom_id),
            )
        return cursor.rowcount > 0

    def reinforce(self, atom_id: int, confidence: float | None = None) -> bool:
        now = int(time())
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT atom_type, importance, confidence, reinforcement_count, status
                FROM memory_atoms
                WHERE id=?
                """,
                (atom_id,),
            ).fetchone()
            if not row or row["status"] == MEMORY_ATOM_STATUS_FORGOTTEN:
                return False
            new_count = int(row["reinforcement_count"]) + 1
            new_ttl, decay_type = compute_atom_ttl(
                str(row["atom_type"]), float(row["importance"]), new_count
            )
            old_confidence = float(row["confidence"])
            new_confidence = old_confidence
            if confidence is not None:
                bounded = min(max(float(confidence), 0.0), 1.0)
                new_confidence = round(old_confidence * 0.7 + bounded * 0.3, 4)
            cursor = conn.execute(
                """
                UPDATE memory_atoms
                SET confidence=?, reinforcement_count=?, ttl_days=?, expires_at=?,
                    decay_type=?, last_reinforced_at=?, last_accessed_at=?,
                    status=?
                WHERE id=?
                """,
                (
                    new_confidence,
                    new_count,
                    new_ttl,
                    now + int(new_ttl * 86400),
                    decay_type,
                    now,
                    now,
                    MEMORY_ATOM_STATUS_ACTIVE,
                    atom_id,
                ),
            )
        return cursor.rowcount > 0

    def expire_stale(self, scope_id: str | None = None) -> int:
        filters = ["status=?", "expires_at<?"]
        params: list[object] = [MEMORY_ATOM_STATUS_ACTIVE, int(time())]
        if scope_id:
            filters.append("scope_id=?")
            params.append(scope_id)
        with self.db.connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE memory_atoms
                SET status=?
                WHERE {" AND ".join(filters)}
                """,
                (MEMORY_ATOM_STATUS_EXPIRED, *params),
            )
        return int(cursor.rowcount)

    def forget_expired(
        self, older_than_days: float = 7.0, scope_id: str | None = None
    ) -> int:
        cutoff = int(time() - max(0.0, older_than_days) * 86400)
        filters = ["status=?", "expires_at<?"]
        params: list[object] = [MEMORY_ATOM_STATUS_EXPIRED, cutoff]
        if scope_id:
            filters.append("scope_id=?")
            params.append(scope_id)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM memory_atoms WHERE {' AND '.join(filters)}",
                params,
            ).fetchall()
            atom_ids = [int(row[0]) for row in rows]
            if not atom_ids:
                return 0
            placeholders = ",".join("?" * len(atom_ids))
            conn.execute(
                f"DELETE FROM memory_atoms_fts WHERE atom_id IN ({placeholders})",
                atom_ids,
            )
            conn.execute(
                f"""
                UPDATE memory_atoms
                SET status=?
                WHERE id IN ({placeholders})
                """,
                (MEMORY_ATOM_STATUS_FORGOTTEN, *atom_ids),
            )
        return len(atom_ids)

    def delete_by_parent(
        self, conn: sqlite3.Connection, parent_memory_id: int
    ) -> int:
        rows = conn.execute(
            "SELECT id FROM memory_atoms WHERE parent_memory_id=?",
            (parent_memory_id,),
        ).fetchall()
        atom_ids = [int(row[0]) for row in rows]
        if atom_ids:
            placeholders = ",".join("?" * len(atom_ids))
            conn.execute(
                f"DELETE FROM memory_atoms_fts WHERE atom_id IN ({placeholders})",
                atom_ids,
            )
            conn.execute(
                f"DELETE FROM memory_atoms WHERE id IN ({placeholders})",
                atom_ids,
            )
        return len(atom_ids)

    def counts(self, scope_id: str | None = None) -> dict[str, int]:
        filters = []
        params: list[object] = []
        if scope_id:
            filters.append("scope_id=?")
            params.append(scope_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        result = {
            "active": 0,
            "expired": 0,
            "forgotten": 0,
            "total": 0,
        }
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT status, COUNT(*) FROM memory_atoms {where} GROUP BY status",
                params,
            ).fetchall()
        for status, count in rows:
            result[str(status)] = int(count)
            result["total"] += int(count)
        return result

    def _insert(
        self,
        conn: sqlite3.Connection,
        parent_memory_id: int,
        scope: str,
        scope_id: str,
        atom_type: str,
        content: str,
        importance: float,
        confidence: float,
        source: str,
        metadata: dict[str, Any],
    ) -> int:
        clean = " ".join(content.split())[:900]
        if not clean:
            return 0
        now = int(time())
        bounded_importance = min(max(float(importance), 0.0), 1.0)
        bounded_confidence = min(max(float(confidence), 0.0), 1.0)
        ttl_days, decay_type = compute_atom_ttl(atom_type, bounded_importance, 0)
        cursor = conn.execute(
            """
            INSERT INTO memory_atoms(
                parent_memory_id, scope, scope_id, atom_type, content, importance,
                confidence, source, created_at, last_accessed_at,
                last_reinforced_at, ttl_days, expires_at, status,
                reinforcement_count, decay_type, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent_memory_id,
                scope,
                scope_id,
                atom_type[:40] or "unknown",
                clean,
                bounded_importance,
                bounded_confidence,
                source[:80],
                now,
                now,
                None,
                ttl_days,
                now + int(ttl_days * 86400),
                MEMORY_ATOM_STATUS_ACTIVE,
                0,
                decay_type,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        atom_id = int(cursor.lastrowid)
        self.fts.insert(conn, atom_id, scope_id, atom_type[:40] or "unknown", clean)
        return atom_id

    def _search_like(
        self,
        conn: sqlite3.Connection,
        scope_id: str,
        terms: list[str],
        limit: int,
        atom_type: str,
    ) -> list[sqlite3.Row]:
        rows: list[sqlite3.Row] = []
        for term in terms[:6]:
            filters = ["scope_id=?", "status='active'", "content LIKE ?"]
            params: list[object] = [scope_id, f"%{term}%"]
            if atom_type:
                filters.append("atom_type=?")
                params.append(atom_type)
            rows.extend(
                conn.execute(
                    f"""
                    SELECT {self._SELECT_COLUMNS}
                    FROM memory_atoms
                    WHERE {" AND ".join(filters)}
                    ORDER BY importance DESC, created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                ).fetchall()
            )
        return rows

    def _dedupe(self, rows: list[sqlite3.Row], limit: int) -> list[MemoryAtomRecord]:
        seen = set()
        records = []
        for row in rows:
            atom_id = int(row[0])
            if atom_id in seen:
                continue
            seen.add(atom_id)
            records.append(MemoryAtomRecord(*row))
            if len(records) >= limit:
                break
        return records

    def _rank_score(self, atom: MemoryAtomRecord) -> tuple[float, float, int]:
        temporal = atom_temporal_score(
            atom.last_accessed_at, atom.ttl_days, atom.decay_type
        )
        final = atom_final_score(
            atom.importance,
            atom.confidence,
            temporal,
            atom.reinforcement_count,
        )
        return final, float(atom.importance), int(atom.created_at)

    def _terms(self, query: str) -> list[str]:
        terms = []
        for raw in query.replace("/", " ").replace("_", " ").split():
            term = raw.strip().lower()
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        return terms
