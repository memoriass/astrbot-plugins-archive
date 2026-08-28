"""Memory-quality feedback queue."""

from __future__ import annotations

import json
from time import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..plugin.db import Database


class FeedbackQueue:

    def __init__(self, db: "Database"):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    processed_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_scope_status
                    ON memory_feedback(scope_id, status, created_at DESC);
                """
            )

    def submit_useful(
        self, scope_id: str, user_id: str, memory_ids: list[int]
    ) -> int | None:
        """Record that certain memories were useful in a retrieval."""
        if not memory_ids:
            return None
        payload = json.dumps({"memory_ids": memory_ids[:20]})
        return self._insert(scope_id, user_id, "useful", payload)

    def submit_not_useful(
        self, scope_id: str, user_id: str, memory_ids: list[int], reason: str = ""
    ) -> int | None:
        """Record that certain memories were not useful."""
        if not memory_ids:
            return None
        payload = json.dumps({"memory_ids": memory_ids[:20], "reason": reason[:200]})
        return self._insert(scope_id, user_id, "not_useful", payload)

    def submit_new_memory(
        self, scope_id: str, user_id: str, content: str, kind: str = ""
    ) -> int | None:
        """Suggest a new memory that should be created."""
        if not content.strip():
            return None
        payload = json.dumps({"content": content[:1000], "kind": kind[:50]})
        return self._insert(scope_id, user_id, "new_memory", payload)

    def submit_merge(
        self,
        scope_id: str,
        user_id: str,
        memory_ids: list[int],
        merged_content: str = "",
    ) -> int | None:
        """Suggest that certain memories should be merged."""
        if len(memory_ids) < 2:
            return None
        payload = json.dumps(
            {
                "memory_ids": memory_ids[:10],
                "merged_content": merged_content[:1000],
            }
        )
        return self._insert(scope_id, user_id, "merge", payload)

    def pending(self, scope_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return pending feedback items."""
        safe_limit = max(1, min(limit, 50))
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT id, scope_id, user_id, kind, payload, status, created_at
                   FROM memory_feedback WHERE scope_id=? AND status='pending'
                   ORDER BY created_at ASC LIMIT ?""",
                (scope_id, safe_limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_processed(self, feedback_id: int) -> bool:
        """Mark a feedback item as processed."""
        now = int(time())
        with self.db.connect() as conn:
            affected = conn.execute(
                "UPDATE memory_feedback SET status='processed', processed_at=? WHERE id=? AND status='pending'",
                (now, feedback_id),
            ).rowcount
        return affected > 0

    def pending_item(self, scope_id: str, feedback_id: int) -> dict[str, Any] | None:
        """Return one pending feedback item within the requested scope."""
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT id, scope_id, user_id, kind, payload, status, created_at
                   FROM memory_feedback
                   WHERE id=? AND scope_id=? AND status='pending'""",
                (feedback_id, scope_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_pending(
        self,
        storage: Any,
        scope_id: str,
        feedback_id: int,
        *,
        content: str = "",
        memory_kind: str = "",
        actor: str = "web",
    ) -> dict[str, Any]:
        """Update user-editable fields on a pending feedback item."""
        item = self.pending_item(scope_id, feedback_id)
        if item is None:
            return {"ok": False, "error": "not_found", "feedback_id": feedback_id}
        kind = str(item.get("kind") or "")
        payload = dict(item.get("payload") or {})
        clean_content = str(content or "").strip()
        if kind == "new_memory":
            if not clean_content:
                return {
                    "ok": False,
                    "error": "empty_content",
                    "feedback_id": feedback_id,
                }
            payload["content"] = clean_content[:1000]
            payload["kind"] = str(memory_kind or payload.get("kind") or "semantic_note")[
                :50
            ]
        elif kind == "merge":
            payload["merged_content"] = clean_content[:1000]
        elif kind == "not_useful":
            payload["reason"] = clean_content[:200]
        else:
            return {
                "ok": False,
                "error": "feedback_not_editable",
                "feedback_id": feedback_id,
                "kind": kind,
            }
        with self.db.connect() as conn:
            affected = conn.execute(
                """UPDATE memory_feedback SET payload=?
                   WHERE id=? AND scope_id=? AND status='pending'""",
                (json.dumps(payload, ensure_ascii=False), feedback_id, scope_id),
            ).rowcount
        if affected <= 0:
            return {"ok": False, "error": "not_found", "feedback_id": feedback_id}
        audit = self._audit_logger(storage)
        if audit is not None:
            audit.record(
                "update_memory_feedback",
                "memory_feedback",
                str(feedback_id),
                f"scope={scope_id} kind={kind}",
                actor,
            )
        return {
            "ok": True,
            "feedback_id": feedback_id,
            "item": self.pending_item(scope_id, feedback_id),
        }

    def dismiss_pending(
        self,
        storage: Any,
        scope_id: str,
        feedback_id: int,
        *,
        actor: str = "web",
    ) -> dict[str, Any]:
        """Dismiss a pending feedback item without applying it."""
        now = int(time())
        with self.db.connect() as conn:
            affected = conn.execute(
                """UPDATE memory_feedback
                   SET status='dismissed', processed_at=?
                   WHERE id=? AND scope_id=? AND status='pending'""",
                (now, feedback_id, scope_id),
            ).rowcount
        if affected <= 0:
            return {"ok": False, "error": "not_found", "feedback_id": feedback_id}
        audit = self._audit_logger(storage)
        if audit is not None:
            audit.record(
                "dismiss_memory_feedback",
                "memory_feedback",
                str(feedback_id),
                f"scope={scope_id}",
                actor,
            )
        return {"ok": True, "feedback_id": feedback_id, "status": "dismissed"}

    def stats(self, scope_id: str) -> dict[str, int]:
        """Return feedback count by kind and status."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT kind, status, COUNT(*) FROM memory_feedback WHERE scope_id=? GROUP BY kind, status",
                (scope_id,),
            ).fetchall()
        result: dict[str, int] = {}
        for row in rows:
            key = f"{row[0]}_{row[1]}"
            result[key] = int(row[2])
        return result

    def active_scope_ids(self, limit: int = 200) -> list[str]:
        """Return scopes that contain feedback, newest first."""
        safe_limit = max(1, min(int(limit or 200), 500))
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT scope_id, MAX(created_at) AS last_seen
                   FROM memory_feedback WHERE scope_id<>''
                   GROUP BY scope_id ORDER BY last_seen DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def cleanup_old(self, max_age_days: int = 60) -> int:
        """Remove processed feedback older than max_age_days."""
        cutoff = int(time()) - max_age_days * 86400
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM memory_feedback WHERE status='processed' AND created_at < ?",
                (cutoff,),
            ).rowcount
        return affected

    def process_pending(
        self,
        storage: Any,
        scope_id: str,
        *,
        limit: int = 20,
        actor: str = "memory_feedback",
    ) -> dict[str, int]:
        """Apply pending feedback after an explicit confirmation boundary."""
        items = self.pending(scope_id, limit=limit)
        return self._process_items(storage, scope_id, items, actor=actor)

    def process_item(
        self,
        storage: Any,
        scope_id: str,
        feedback_id: int,
        *,
        actor: str = "memory_feedback",
    ) -> dict[str, Any]:
        """Apply one pending feedback item after explicit confirmation."""
        item = self.pending_item(scope_id, feedback_id)
        if item is None:
            return {
                **self._empty_process_stats(),
                "error": "not_found",
                "feedback_id": feedback_id,
            }
        return {
            **self._process_items(storage, scope_id, [item], actor=actor),
            "feedback_id": feedback_id,
        }

    def _process_items(
        self,
        storage: Any,
        scope_id: str,
        items: list[dict[str, Any]],
        *,
        actor: str,
    ) -> dict[str, int]:
        stats = self._empty_process_stats()
        for item in items:
            kind = str(item.get("kind") or "")
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            handled = False
            if kind == "useful":
                count = self._adjust_importance(
                    scope_id, payload.get("memory_ids"), 0.05
                )
                stats["boosted"] += count
                handled = count > 0
            elif kind == "not_useful":
                count = self._adjust_importance(
                    scope_id, payload.get("memory_ids"), -0.08
                )
                stats["reduced"] += count
                handled = count > 0
            elif kind == "new_memory":
                content = str(payload.get("content") or "").strip()
                if content:
                    memory_kind = str(payload.get("kind") or "semantic_note")[:50]
                    storage.add_memory(
                        "session",
                        scope_id,
                        memory_kind,
                        content,
                        0.56,
                        "memory_feedback",
                    )
                    storage.upsert_semantic(
                        scope_id,
                        str(item.get("user_id") or actor),
                        "feedback_note",
                        content,
                        0.62,
                        "memory_feedback",
                    )
                    stats["created"] += 1
                    handled = True
            elif kind == "merge":
                content = self._merged_content(scope_id, payload)
                if content:
                    storage.add_memory(
                        "session",
                        scope_id,
                        "semantic_note",
                        content,
                        0.64,
                        "memory_feedback_merge",
                    )
                    stats["merged"] += 1
                    handled = True
            if handled and self.mark_processed(int(item["id"])):
                stats["processed"] += 1
            else:
                stats["skipped"] += 1
        audit = self._audit_logger(storage)
        if stats["processed"] and audit is not None:
            audit.record(
                "process_memory_feedback",
                "memory_feedback",
                scope_id,
                json.dumps(stats, ensure_ascii=False),
                actor,
            )
        return stats

    @staticmethod
    def _empty_process_stats() -> dict[str, int]:
        return {
            "processed": 0,
            "boosted": 0,
            "reduced": 0,
            "created": 0,
            "merged": 0,
            "skipped": 0,
        }

    def _audit_logger(self, storage: Any) -> Any | None:
        if hasattr(storage, "audit"):
            return storage.audit
        memory_storage = getattr(storage, "memory_storage", None)
        if memory_storage is not None and hasattr(memory_storage, "audit"):
            return memory_storage.audit
        return None

    def _insert(self, scope_id: str, user_id: str, kind: str, payload: str) -> int:
        now = int(time())
        with self.db.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO memory_feedback(scope_id, user_id, kind, payload, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (scope_id, user_id[:200], kind, payload, now),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def _adjust_importance(
        self, scope_id: str, raw_ids: object, delta: float
    ) -> int:
        ids = self._memory_ids(raw_ids)
        if not ids:
            return 0
        changed = 0
        with self.db.connect() as conn:
            for memory_id in ids:
                row = conn.execute(
                    "SELECT importance FROM episodic_memories WHERE id=? AND scope_id=?",
                    (memory_id, scope_id),
                ).fetchone()
                if not row:
                    continue
                importance = min(max(float(row[0]) + delta, 0.0), 1.0)
                conn.execute(
                    "UPDATE episodic_memories SET importance=? WHERE id=? AND scope_id=?",
                    (importance, memory_id, scope_id),
                )
                changed += 1
        return changed

    def _merged_content(self, scope_id: str, payload: dict[str, Any]) -> str:
        merged = str(payload.get("merged_content") or "").strip()
        if merged:
            return merged[:1000]
        ids = self._memory_ids(payload.get("memory_ids"))
        if len(ids) < 2:
            return ""
        placeholders = ",".join("?" * len(ids))
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT content FROM episodic_memories WHERE scope_id=? AND id IN ({placeholders})",  # noqa: S608
                [scope_id, *ids],
            ).fetchall()
        parts = [" ".join(str(row[0]).split()) for row in rows if str(row[0]).strip()]
        return " | ".join(parts)[:1000]

    def _memory_ids(self, raw_ids: object) -> list[int]:
        if not isinstance(raw_ids, list):
            return []
        ids = []
        for item in raw_ids[:20]:
            try:
                memory_id = int(item)
            except (TypeError, ValueError):
                continue
            if memory_id > 0 and memory_id not in ids:
                ids.append(memory_id)
        return ids

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        payload_raw = row[4]
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except (json.JSONDecodeError, TypeError):
            payload = {"raw": payload_raw}
        return {
            "id": row[0],
            "scope_id": row[1],
            "user_id": row[2],
            "kind": row[3],
            "payload": payload,
            "status": row[5],
            "created_at": row[6],
        }
