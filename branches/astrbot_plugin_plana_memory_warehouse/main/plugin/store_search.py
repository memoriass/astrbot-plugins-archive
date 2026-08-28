from __future__ import annotations

import sqlite3
from typing import Any

from .store_common import CONTRACT_VERSION, fts_query, like_pattern, merge_rows, query_terms


class MemoryWarehouseSearchMixin:
    def search(
        self,
        *,
        query: str = "",
        scope_id: str = "",
        scope_ids: list[str] | str | None = None,
        shared_scope_ids: list[str] | str | None = None,
        unified_msg_origin: str = "",
        actor_id: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        safe_limit = self._safe_int(limit, 10, 1, 200)
        scopes = self._scope_filters(scope_id, scope_ids, shared_scope_ids)
        origin = self._bounded(unified_msg_origin, 260)
        actor = self._bounded(actor_id, 200)
        text_query = " ".join(str(query or "").split())[:500]
        if not text_query:
            rows = self._search_like("", scopes, origin, actor, safe_limit)
            source = "recent"
        else:
            rows = self._search_fts(text_query, scopes, origin, actor, safe_limit)
            source = "fts"
            if rows is None:
                rows = self._search_like(text_query, scopes, origin, actor, safe_limit)
                source = "like"
            elif len(rows) < safe_limit:
                rows = merge_rows(
                    rows,
                    self._search_like(text_query, scopes, origin, actor, safe_limit),
                    safe_limit,
                )
                source = "hybrid"
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "coverage_status": "warehouse_index",
            "source": source,
            "query": text_query,
            "scope_id": scopes[0] if len(scopes) == 1 else "",
            "scope_ids": scopes,
            "count": len(rows),
            "results": [self._row(row, snippet=True) for row in rows],
        }

    def recent(
        self,
        *,
        scope_id: str = "",
        scope_ids: list[str] | str | None = None,
        shared_scope_ids: list[str] | str | None = None,
        unified_msg_origin: str = "",
        actor_id: str = "",
        role: str = "",
        event_type: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        safe_limit = self._safe_int(limit, 20, 1, 200)
        clauses: list[str] = []
        params: list[Any] = []
        scopes = self._scope_filters(scope_id, scope_ids, shared_scope_ids)
        filters = {
            "unified_msg_origin": self._bounded(unified_msg_origin, 260),
            "actor_id": self._bounded(actor_id, 200),
            "role": self._bounded(role, 40),
            "event_type": self._bounded(event_type, 80),
        }
        self._append_scope_clause(clauses, params, "scope_id", scopes)
        for column, value in filters.items():
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(safe_limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM warehouse_events
                    {where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?""",
                params,
            ).fetchall()
        return {
            "ok": True,
            "contract_version": CONTRACT_VERSION,
            "coverage_status": "warehouse_index",
            "scope_id": scopes[0] if len(scopes) == 1 else "",
            "scope_ids": scopes,
            "count": len(rows),
            "results": [self._row(row, snippet=True) for row in rows],
        }

    def _search_fts(
        self,
        query: str,
        scope_ids: list[str],
        origin: str,
        actor_id: str,
        limit: int,
    ) -> list[sqlite3.Row] | None:
        fts = fts_query(query)
        if not fts:
            return self._search_like("", scope_ids, origin, actor_id, limit)
        clauses = ["warehouse_events_fts.content MATCH ?"]
        params: list[Any] = [fts]
        self._append_scope_clause(clauses, params, "e.scope_id", scope_ids)
        if origin:
            clauses.append("e.unified_msg_origin=?")
            params.append(origin)
        if actor_id:
            clauses.append("e.actor_id=?")
            params.append(actor_id)
        params.append(limit)
        sql = f"""
            SELECT e.* FROM warehouse_events_fts
            JOIN warehouse_events e ON e.id=warehouse_events_fts.rowid
            WHERE {' AND '.join(clauses)}
            ORDER BY bm25(warehouse_events_fts), e.created_at DESC
            LIMIT ?
        """
        try:
            with self._connect() as conn:
                return conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return None

    def _search_like(
        self,
        query: str,
        scope_ids: list[str],
        origin: str,
        actor_id: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        terms = query_terms(query)
        if terms:
            for term in terms:
                clauses.append("content LIKE ? ESCAPE '\\'")
                params.append(like_pattern(term))
        elif query:
            clauses.append("content LIKE ? ESCAPE '\\'")
            params.append(like_pattern(query))
        self._append_scope_clause(clauses, params, "scope_id", scope_ids)
        if origin:
            clauses.append("unified_msg_origin=?")
            params.append(origin)
        if actor_id:
            clauses.append("actor_id=?")
            params.append(actor_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            return conn.execute(
                f"""SELECT * FROM warehouse_events
                    {where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?""",
                params,
            ).fetchall()

    def _scope_filters(
        self,
        scope_id: str = "",
        scope_ids: list[str] | str | None = None,
        shared_scope_ids: list[str] | str | None = None,
    ) -> list[str]:
        values = []
        values.extend(self._string_list(scope_id))
        values.extend(self._string_list(scope_ids))
        values.extend(self._string_list(shared_scope_ids))
        seen: set[str] = set()
        scopes: list[str] = []
        for value in values:
            clean = self._bounded(value, 200)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            scopes.append(clean)
            if len(scopes) >= 20:
                break
        return scopes

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = str(value or "").replace(";", ",").split(",")
        return [str(item or "").strip() for item in items if str(item or "").strip()]

    @staticmethod
    def _append_scope_clause(
        clauses: list[str],
        params: list[Any],
        column: str,
        scope_ids: list[str],
    ) -> None:
        if not scope_ids:
            return
        if len(scope_ids) == 1:
            clauses.append(f"{column}=?")
            params.append(scope_ids[0])
            return
        placeholders = ", ".join("?" for _ in scope_ids)
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(scope_ids)
