from __future__ import annotations

import sqlite3
from time import time

from .models import MemoryAtomRecord, MemoryRecord, SemanticMemory


class MemoryStorageOperationsMixin:
    _SEMANTIC_HISTORY_RETENTION_DAYS = 180
    _SEMANTIC_HISTORY_MAX_PER_KEY = 50

    @staticmethod
    def _append_semantic_history(
        conn,
        scope_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
        event_type: str,
        replacement_value: str,
        created_at: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO semantic_memory_history(
                scope_id, subject, predicate, object_value, confidence,
                source, event_type, replacement_value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope_id,
                subject,
                predicate,
                object_value,
                confidence,
                source,
                event_type,
                replacement_value,
                created_at,
            ),
        )

    def semantic_history(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT object_value, confidence, source, event_type,
                       replacement_value, created_at
                FROM semantic_memory_history
                WHERE scope_id=? AND subject=? AND predicate=?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (scope_id, subject[:160], predicate[:80], safe_limit),
            ).fetchall()
        return [
            {
                "object_value": row[0],
                "confidence": float(row[1]),
                "source": row[2],
                "event_type": row[3],
                "replacement_value": row[4],
                "created_at": int(row[5]),
            }
            for row in rows
        ]

    def prune_semantic_history(
        self,
        scope_id: str,
        *,
        retention_days: int = _SEMANTIC_HISTORY_RETENTION_DAYS,
        max_per_key: int = _SEMANTIC_HISTORY_MAX_PER_KEY,
    ) -> dict[str, int]:
        safe_days = max(1, min(int(retention_days), 3650))
        safe_max = max(1, min(int(max_per_key), 1000))
        cutoff = int(time()) - safe_days * 86400
        with self._connect() as conn:
            deleted_by_age = conn.execute(
                """DELETE FROM semantic_memory_history
                   WHERE scope_id=? AND created_at<?""",
                (scope_id, cutoff),
            ).rowcount
            deleted_excess = conn.execute(
                """DELETE FROM semantic_memory_history
                   WHERE id IN (
                       SELECT id FROM (
                           SELECT id, ROW_NUMBER() OVER (
                               PARTITION BY scope_id, subject, predicate
                               ORDER BY created_at DESC, id DESC
                           ) AS row_number
                           FROM semantic_memory_history
                           WHERE scope_id=?
                       ) ranked
                       WHERE row_number>?
                   )""",
                (scope_id, safe_max),
            ).rowcount
            retained = int(
                conn.execute(
                    "SELECT COUNT(*) FROM semantic_memory_history WHERE scope_id=?",
                    (scope_id,),
                ).fetchone()[0]
            )
        return {
            "deleted_by_age": max(0, int(deleted_by_age)),
            "deleted_excess": max(0, int(deleted_excess)),
            "retained": retained,
            "retention_days": safe_days,
            "max_per_key": safe_max,
        }

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

    def atoms_for_memory(self, parent_memory_id: int) -> list[MemoryAtomRecord]:
        return self.atoms.atoms_for_memory(parent_memory_id)

    def active_scope_ids(
        self,
        limit: int = 20,
        *,
        since_ts: int | None = None,
    ) -> list[str]:
        try:
            parsed_limit = int(limit or 20)
        except (TypeError, ValueError):
            parsed_limit = 20
        safe_limit = max(1, min(parsed_limit, 500))
        cutoff = max(0, int(since_ts or 0))
        sources = (
            ("episodic_memories", "created_at"),
            ("semantic_memories", "updated_at"),
            ("memory_atoms", "created_at"),
        )
        scores: dict[str, int] = {}
        with self._connect() as conn:
            for table, column in sources:
                where = "WHERE scope_id<>''"
                params: tuple[object, ...] = ()
                if cutoff:
                    where += f" AND {column}>=?"
                    params = (cutoff,)
                try:
                    rows = conn.execute(
                        f"""
                        SELECT scope_id, MAX({column}) AS last_seen
                        FROM {table}
                        {where}
                        GROUP BY scope_id
                        """,
                        params,
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                for row in rows:
                    scope_id = str(row[0] or "").strip()
                    if not scope_id:
                        continue
                    scores[scope_id] = max(scores.get(scope_id, 0), int(row[1] or 0))
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [scope_id for scope_id, _last_seen in ordered[:safe_limit]]

    def search_atoms(
        self, scope_id: str, query: str, limit: int, atom_type: str = ""
    ) -> list[MemoryAtomRecord]:
        return self.atoms.search(scope_id, query, limit, atom_type)

    def recent_atoms(
        self, scope_id: str, limit: int, atom_type: str = ""
    ) -> list[MemoryAtomRecord]:
        return self.atoms.recent(scope_id, limit, atom_type)

    def reinforce_atom(self, atom_id: int, confidence: float | None = None) -> bool:
        return self.atoms.reinforce(atom_id, confidence)

    def expire_stale_atoms(self, scope_id: str | None = None) -> int:
        return self.atoms.expire_stale(scope_id)

    def forget_expired_atoms(
        self, older_than_days: float = 7.0, scope_id: str | None = None
    ) -> int:
        return self.atoms.forget_expired(older_than_days, scope_id)

    def decay_candidates(
        self, scope_id: str, limit: int, min_importance: float
    ) -> list[MemoryRecord]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                self._memory_select()
                + " WHERE scope_id=? AND importance>? ORDER BY importance ASC, created_at ASC, id ASC LIMIT ?",
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
            active_atoms = conn.execute(
                "SELECT COUNT(*) FROM memory_atoms WHERE scope_id=? AND status='active'",
                (scope_id,),
            ).fetchone()[0]
        return {
            "episodic": int(episodic),
            "semantic": int(semantic),
            "tool_user": int(tool_user),
            "decay_events": int(decay_events),
            "active_atoms": int(active_atoms),
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

    # -- Destructive operations with transaction protection + audit --

    def delete_memory(self, memory_id: int, actor: str = "web") -> dict[str, object]:
        """Delete an episodic memory by ID with cascading link/decay cleanup."""
        with self._connect() as conn:
            row = conn.execute(
                self._memory_select() + " WHERE id=?",
                (memory_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found", "id": memory_id}
            record = MemoryRecord(*row)
            conn.execute("DELETE FROM memory_links WHERE memory_id=?", (memory_id,))
            conn.execute(
                "DELETE FROM memory_decay_events WHERE memory_id=?", (memory_id,)
            )
            self.atoms.delete_by_parent(conn, memory_id)
            self.fts.delete(conn, memory_id)
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
