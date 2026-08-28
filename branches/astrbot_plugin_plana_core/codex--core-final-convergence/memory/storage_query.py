from __future__ import annotations

from .models import MemoryRecord, SemanticMemory


class MemoryStorageQueryMixin:
    def search_memories(
        self, scope_id: str, query: str, limit: int
    ) -> list[MemoryRecord]:
        if limit <= 0:
            return []
        terms = self._terms(query)
        if not terms:
            return self.recent_memories(scope_id, limit)
        with self._connect() as conn:
            candidate_limit = max(limit * 2, limit + 4)
            rows = self.fts.search(conn, scope_id, terms, candidate_limit)
            rows.extend(self._search_like(conn, scope_id, terms, candidate_limit))
        return self._dedupe_memories(rows, limit)

    def recent_memories(self, scope_id: str, limit: int) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                self._memory_select()
                + " WHERE scope_id=? ORDER BY created_at DESC, id DESC LIMIT ?",
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
                self._memory_select()
                + " WHERE scope_id=? AND kind=? ORDER BY created_at DESC, id DESC LIMIT ?",
                (scope_id, kind.strip(), limit),
            ).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def search_memories_by_actor(
        self,
        actor_id: str,
        query: str,
        limit: int,
        *,
        scope_id: str = "",
    ) -> list[MemoryRecord]:
        if limit <= 0 or not actor_id.strip():
            return []
        terms = self._terms(query)
        filters = ["actor_id=?"]
        params: list[object] = [actor_id.strip()]
        if scope_id:
            filters.append("scope_id=?")
            params.append(scope_id)
        if terms:
            like = " OR ".join(["content LIKE ?" for _ in terms[:6]])
            filters.append(f"({like})")
            params.extend(f"%{term}%" for term in terms[:6])
        with self._connect() as conn:
            rows = conn.execute(
                self._memory_select()
                + f""" WHERE {" AND ".join(filters)}
                       ORDER BY importance DESC, created_at DESC, id DESC
                       LIMIT ?""",
                (*params, max(1, min(limit, 100))),
            ).fetchall()
        return [MemoryRecord(*row) for row in rows]

    def search_memories_by_kind(
        self, scope_id: str, query: str, kind: str, limit: int
    ) -> list[MemoryRecord]:
        if limit <= 0:
            return []
        if not kind.strip():
            return self.search_memories(scope_id, query, limit)
        terms = self._terms(query)
        if not terms:
            return self.recent_memories_by_kind(scope_id, kind, limit)
        with self._connect() as conn:
            candidate_limit = max(limit * 2, limit + 4)
            rows = self.fts.search(conn, scope_id, terms, candidate_limit, kind.strip())
            rows.extend(
                self._search_like(conn, scope_id, terms, candidate_limit, kind.strip())
            )
        return self._dedupe_memories(rows, limit)

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

    @staticmethod
    def _memory_select(alias: str = "") -> str:
        prefix = f"{alias}." if alias else ""
        table = "episodic_memories " + alias if alias else "episodic_memories"
        return (
            f"SELECT {prefix}id, {prefix}scope, {prefix}scope_id, {prefix}kind, "
            f"{prefix}content, {prefix}importance, {prefix}source, "
            f"{prefix}created_at, {prefix}actor_id, {prefix}subject FROM {table}"
        )

    def _terms(self, query: str) -> list[str]:
        terms = []
        for raw in query.replace("/", " ").replace("_", " ").split():
            term = raw.strip().lower()
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        return terms

    def _search_like(
        self,
        conn,
        scope_id: str,
        terms: list[str],
        limit: int,
        kind: str = "",
    ) -> list:
        rows: list = []
        for term in terms[:6]:
            filters = ["scope_id=?", "content LIKE ?"]
            params: list[object] = [scope_id, f"%{term}%"]
            if kind:
                filters.append("kind=?")
                params.append(kind)
            rows.extend(
                conn.execute(
                    f"""
                    {self._memory_select()}
                    WHERE {" AND ".join(filters)}
                    ORDER BY importance DESC, created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                ).fetchall()
            )
        return rows
