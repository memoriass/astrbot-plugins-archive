from __future__ import annotations

import json
from time import time
from typing import Any

from .delivery import normalize_delivery_context
from .remote_task_execution_state import (
    RemoteTaskObservationStoreMixin,
    merge_execution_state,
)

from ..plugin.db import Database


def bounded_json_object(value: Any, max_chars: int = 16000) -> str:
    limit = max(2, int(max_chars or 16000))
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError, OverflowError):
        serialized = ""
    if serialized and len(serialized) <= limit:
        return serialized

    source = value if isinstance(value, dict) else {}
    compact: dict[str, Any] = {"truncated": True}
    for key in ("status", "request_id", "result_summary", "error"):
        if key in source:
            compact[key] = _compact_scalar(source.get(key))
    if "artifacts" in source:
        compact["artifacts"] = _compact_artifacts(source.get("artifacts"))

    nested = source.get("result")
    if isinstance(nested, dict):
        compact_result: dict[str, Any] = {}
        for key in ("count", "returned_count"):
            if key in nested:
                compact_result[key] = nested.get(key)
        subscriptions = nested.get("subscriptions")
        if isinstance(subscriptions, list):
            compact_result["subscriptions"] = [
                _compact_subscription(item) for item in subscriptions[:5]
            ]
            compact_result["subscriptions_total"] = len(subscriptions)
        if compact_result:
            compact["result"] = compact_result

    candidate = json.dumps(compact, ensure_ascii=False, default=str)
    if len(candidate) <= limit:
        return candidate
    fallback = {
        "truncated": True,
        "status": _compact_scalar(source.get("status"), 80),
        "request_id": _compact_scalar(source.get("request_id"), 120),
        "result_summary": _compact_scalar(source.get("result_summary"), 240),
        "error": _compact_scalar(source.get("error"), 240),
    }
    fallback = {key: item for key, item in fallback.items() if item not in ("", None)}
    candidate = json.dumps(fallback, ensure_ascii=False, default=str)
    return candidate if len(candidate) <= limit else "{}"


def _compact_scalar(value: Any, max_chars: int = 500) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return " ".join(str(value).split())[:max_chars]


def _compact_artifacts(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        return {"count": 0}
    entries = []
    for item in value[:8]:
        if isinstance(item, dict):
            entries.append(
                {
                    key: _compact_scalar(item.get(key), 240)
                    for key in ("id", "name", "title", "type", "url", "path", "status")
                    if item.get(key) not in (None, "")
                }
            )
        else:
            entries.append(_compact_scalar(item, 240))
    return {"count": len(value), "items": entries}


def _compact_subscription(value: Any) -> Any:
    if not isinstance(value, dict):
        return _compact_scalar(value, 240)
    return {
        key: _compact_scalar(value.get(key), 240)
        for key in ("id", "title", "name", "season", "status", "url")
        if value.get(key) not in (None, "")
    }


class RemoteTaskRunStore(RemoteTaskObservationStoreMixin):
    """Tracks Codex Runner tasks without making Core an execution runtime."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS remote_task_runs (
                    request_id TEXT PRIMARY KEY,
                    proactive_task_id INTEGER,
                    scope_id TEXT NOT NULL DEFAULT 'global',
                    actor_id TEXT NOT NULL DEFAULT '',
                    delivery_context TEXT NOT NULL DEFAULT '{}',
                    lane TEXT NOT NULL DEFAULT 'interactive',
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    payload TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    runner_run_id TEXT NOT NULL DEFAULT '',
                    execution_state TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_remote_task_scope_status
                    ON remote_task_runs(scope_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_remote_task_lane_status
                    ON remote_task_runs(lane, status, updated_at);
                """
            )
            self._ensure_columns(conn)

    def create(
        self,
        *,
        request_id: str,
        proactive_task_id: int,
        scope_id: str,
        actor_id: str,
        lane: str,
        title: str,
        payload: dict[str, Any],
    ) -> None:
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO remote_task_runs (
                    request_id, proactive_task_id, scope_id, actor_id, delivery_context, lane,
                    title, status, payload, result, runner_run_id, execution_state,
                    error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id[:120],
                    proactive_task_id,
                    scope_id[:200] or "global",
                    actor_id[:200],
                    bounded_json_object(
                        normalize_delivery_context(payload.get("delivery_context"))
                    ),
                    lane[:40] or "interactive",
                    title[:180],
                    "queued",
                    bounded_json_object(payload),
                    "{}",
                    "",
                    "{}",
                    "",
                    now,
                    now,
                ),
            )

    def mark_submitted(
        self,
        request_id: str,
        *,
        runner_run_id: str = "",
        status: str = "submitted",
        result: dict[str, Any] | None = None,
    ) -> bool:
        return self.update(
            request_id,
            status=status,
            runner_run_id=runner_run_id,
            result=result,
        )

    def mark_submitted_if_nonterminal(
        self,
        request_id: str,
        *,
        runner_run_id: str = "",
        result: dict[str, Any] | None = None,
    ) -> bool:
        if not request_id:
            return False
        now = int(time())
        result_json = bounded_json_object(result or {})
        with self.db.connect() as conn:
            affected = conn.execute(
                """
                UPDATE remote_task_runs
                SET status='submitted',
                    runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                    error='', result=?, updated_at=?
                WHERE request_id=?
                  AND status NOT IN ('succeeded', 'failed', 'cancelled')
                """,
                (runner_run_id[:200], result_json, now, request_id[:120]),
            ).rowcount
        return affected > 0

    def update(
        self,
        request_id: str,
        *,
        status: str,
        runner_run_id: str = "",
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> bool:
        if not request_id:
            return False
        now = int(time())
        result_json = bounded_json_object(result or {})
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT execution_state FROM remote_task_runs WHERE request_id=?",
                (request_id[:120],),
            ).fetchone()
            execution_state = merge_execution_state(
                self._json(row[0]) if row is not None else {},
                result,
                cancel_requested=status == "cancelling",
                terminal=status in {"succeeded", "failed", "cancelled", "cancel_failed"},
                now=now,
            )
            affected = conn.execute(
                """
                UPDATE remote_task_runs
                SET status=?, runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                    error=?, result=?, execution_state=?, updated_at=?
                WHERE request_id=?
                """,
                (
                    status[:40],
                    runner_run_id[:200],
                    " ".join(str(error or "").split())[:500],
                    result_json,
                    bounded_json_object(execution_state, 4000),
                    now,
                    request_id[:120],
                ),
            ).rowcount
        return affected > 0

    def apply_terminal_result(
        self,
        request_id: str,
        *,
        status: str,
        runner_run_id: str = "",
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> str:
        """Apply a Runner terminal state without reviving cancelled work."""
        if not request_id:
            return "missing"
        incoming = str(status or "failed").strip().lower()
        if incoming not in {"succeeded", "failed", "cancelled"}:
            incoming = "failed"
        now = int(time())
        result_json = bounded_json_object(result or {})
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT status, execution_state FROM remote_task_runs WHERE request_id=?",
                (request_id[:120],),
            ).fetchone()
            if row is None:
                return "missing"
            current = str(row[0] or "")
            execution_state = merge_execution_state(
                self._json(row[1]), result, terminal=True, now=now
            )
            if current == "cancelled":
                return "ignored_cancelled"
            if current == "cancelling" and incoming == "succeeded":
                conn.execute(
                    """
                    UPDATE remote_task_runs
                    SET status='cancel_failed',
                        runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                        error='late_success_after_cancel', result=?, execution_state=?, updated_at=?
                    WHERE request_id=? AND status='cancelling'
                    """,
                    (
                        runner_run_id[:200], result_json,
                        bounded_json_object(execution_state, 4000), now, request_id[:120],
                    ),
                )
                return "late_success_after_cancel"
            final_status = "cancelled" if incoming == "cancelled" else incoming
            affected = conn.execute(
                """
                UPDATE remote_task_runs
                SET status=?, runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                    error=?, result=?, execution_state=?, updated_at=?
                WHERE request_id=?
                  AND status NOT IN ('succeeded', 'failed', 'cancelled', 'cancel_failed')
                """,
                (
                    final_status,
                    runner_run_id[:200],
                    " ".join(str(error or "").split())[:500],
                    result_json,
                    bounded_json_object(execution_state, 4000),
                    now,
                    request_id[:120],
                ),
            ).rowcount
        return "applied" if affected > 0 else "ignored_terminal"

    def get(self, request_id: str) -> dict[str, Any] | None:
        if not request_id:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT request_id, proactive_task_id, scope_id, actor_id, delivery_context, lane,
                       title, status, result, runner_run_id, error, execution_state,
                       created_at, updated_at
                FROM remote_task_runs
                WHERE request_id=?
                """,
                (request_id[:120],),
            ).fetchone()
        return self._row(row) if row is not None else None

    def audit_context(self, request_id: str) -> dict[str, Any]:
        if not request_id:
            return {}
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload, lane FROM remote_task_runs WHERE request_id=?",
                (request_id[:120],),
            ).fetchone()
        if row is None:
            return {}
        payload = self._json(row[0])
        return {
            "lane": str(row[1] or payload.get("lane") or "")[:80],
            "capability": str(payload.get("capability") or "")[:160],
        }

    def recent(self, *, scope_id: str = "", limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 10), 50))
        with self.db.connect() as conn:
            if scope_id:
                rows = conn.execute(
                    """
                    SELECT request_id, proactive_task_id, scope_id, actor_id, delivery_context, lane,
                           title, status, result, runner_run_id, error, execution_state,
                           created_at, updated_at
                    FROM remote_task_runs
                    WHERE scope_id=?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (scope_id[:200], safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT request_id, proactive_task_id, scope_id, actor_id, delivery_context, lane,
                           title, status, result, runner_run_id, error, execution_state,
                           created_at, updated_at
                    FROM remote_task_runs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [self._row(row) for row in rows]

    def active(
        self,
        *,
        scope_id: str,
        actor_id: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 5), 20))
        params: list[Any] = [scope_id[:200] or "global"]
        actor_clause = ""
        if actor_id:
            actor_clause = " AND actor_id=?"
            params.append(actor_id[:200])
        params.extend(["queued", "submitted", "running", "cancelling", safe_limit])
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT request_id, proactive_task_id, scope_id, actor_id, delivery_context, lane,
                       title, status, result, runner_run_id, error, execution_state,
                       created_at, updated_at
                FROM remote_task_runs
                WHERE scope_id=?{actor_clause}
                  AND status IN (?, ?, ?, ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            statuses = conn.execute(
                "SELECT status, COUNT(*) FROM remote_task_runs GROUP BY status"
            ).fetchall()
            lanes = conn.execute(
                "SELECT lane, status, COUNT(*) FROM remote_task_runs GROUP BY lane, status"
            ).fetchall()
        lane_stats: dict[str, dict[str, int]] = {}
        for row in lanes:
            lane_stats.setdefault(str(row[0]), {})[str(row[1])] = int(row[2])
        return {
            "statuses": {str(row[0]): int(row[1]) for row in statuses},
            "lanes": lane_stats,
            "recent": self.recent(limit=8),
        }

    def _row(self, row: Any) -> dict[str, Any]:
        return {
            "request_id": row[0],
            "proactive_task_id": row[1],
            "scope_id": row[2],
            "actor_id": row[3],
            "delivery_context": self._json(row[4]),
            "lane": row[5],
            "title": row[6],
            "status": row[7],
            "result": self._json(row[8]),
            "runner_run_id": row[9],
            "error": row[10],
            "execution_state": self._json(row[11]),
            "created_at": row[12],
            "updated_at": row[13],
        }

    def _ensure_columns(self, conn: Any) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(remote_task_runs)").fetchall()
        }
        if "delivery_context" not in columns:
            conn.execute(
                "ALTER TABLE remote_task_runs ADD COLUMN delivery_context TEXT NOT NULL DEFAULT '{}'"
            )
        if "execution_state" not in columns:
            conn.execute(
                "ALTER TABLE remote_task_runs ADD COLUMN execution_state TEXT NOT NULL DEFAULT '{}'"
            )

    def _json(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
