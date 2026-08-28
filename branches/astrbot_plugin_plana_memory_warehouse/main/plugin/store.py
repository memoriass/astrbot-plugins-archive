from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .store_common import (
    CONTRACT_VERSION,
    DEFAULT_BULK_LIMIT,
    _like_pattern,
    bounded_metadata,
    clean_evidence_id,
    json_object,
)
from .store_maintenance import MemoryWarehouseMaintenanceMixin
from .store_schema import initialize_schema
from .store_search import MemoryWarehouseSearchMixin

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_BULK_LIMIT",
    "MemoryWarehouseStore",
    "_like_pattern",
]


class MemoryWarehouseStore(
    MemoryWarehouseSearchMixin,
    MemoryWarehouseMaintenanceMixin,
):
    """Long-lived raw episodic evidence warehouse for Plana-family plugins."""

    def __init__(self, data_dir: str | Path, *, max_content_chars: int = 4000) -> None:
        self.root = Path(data_dir)
        self.db_path = self.root / "memory_warehouse.sqlite3"
        self.max_content_chars = max(200, min(int(max_content_chars), 100_000))

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            initialize_schema(conn)

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = self._clean_content(payload.get("content"))
        if not content:
            return self._error("empty_content")

        now = self._now()
        created_at = self._safe_int(payload.get("created_at"), now, 0, now + 86_400)
        scope_id = self._bounded(payload.get("scope_id"), 200)
        origin = self._bounded(payload.get("unified_msg_origin"), 260)
        platform = self._bounded(payload.get("platform"), 80)
        message_type = self._bounded(payload.get("message_type"), 80)
        session_id = self._bounded(payload.get("session_id"), 200)
        group_id = self._bounded(payload.get("group_id"), 200)
        actor_id = self._bounded(payload.get("actor_id"), 200)
        actor_name = self._bounded(payload.get("actor_name"), 160)
        role = self._bounded(payload.get("role") or "user", 40)
        event_type = self._bounded(payload.get("event_type") or "message", 80)
        external_event_id = self._bounded(payload.get("external_event_id"), 260)
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata_json = json.dumps(bounded_metadata(metadata), ensure_ascii=False)
        content_hash = self._content_hash(content)
        evidence_id = self._evidence_id(
            payload,
            scope_id=scope_id,
            origin=origin,
            actor_id=actor_id,
            role=role,
            event_type=event_type,
            external_event_id=external_event_id,
            created_at=created_at,
            content_hash=content_hash,
        )

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM warehouse_events WHERE evidence_id=?",
                (evidence_id,),
            ).fetchone()
            if existing:
                row_id = int(existing["id"])
                conn.execute(
                    """UPDATE warehouse_events
                       SET external_event_id=?,
                           scope_id=?,
                           unified_msg_origin=?,
                           platform=?,
                           message_type=?,
                           session_id=?,
                           group_id=?,
                           actor_id=?,
                           actor_name=?,
                           role=?,
                           event_type=?,
                           content=?,
                           content_hash=?,
                           metadata_json=?,
                           created_at=?,
                           updated_at=?
                       WHERE id=?""",
                    (
                        external_event_id,
                        scope_id,
                        origin,
                        platform,
                        message_type,
                        session_id,
                        group_id,
                        actor_id,
                        actor_name,
                        role,
                        event_type,
                        content,
                        content_hash,
                        metadata_json,
                        created_at,
                        now,
                        row_id,
                    ),
                )
                created = False
            else:
                row_id = self._insert_event(
                    conn,
                    evidence_id=evidence_id,
                    external_event_id=external_event_id,
                    scope_id=scope_id,
                    origin=origin,
                    platform=platform,
                    message_type=message_type,
                    session_id=session_id,
                    group_id=group_id,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    role=role,
                    event_type=event_type,
                    content=content,
                    content_hash=content_hash,
                    metadata_json=metadata_json,
                    created_at=created_at,
                    updated_at=now,
                )
                created = True
            self._replace_fts(
                conn,
                row_id=row_id,
                content=content,
                evidence_id=evidence_id,
                scope_id=scope_id,
                role=role,
                event_type=event_type,
            )
        return {
            "ok": True,
            "created": created,
            "updated": not created,
            "contract_version": CONTRACT_VERSION,
            "evidence_id": evidence_id,
            "event": self.get(evidence_id),
        }

    def bulk_ingest(
        self,
        items: list[dict[str, Any]],
        *,
        max_items: int = DEFAULT_BULK_LIMIT,
    ) -> dict[str, Any]:
        if not isinstance(items, list):
            return self._error("items_must_be_array")
        safe_limit = self._safe_int(max_items, DEFAULT_BULK_LIMIT, 1, 5000)
        accepted = created = updated = 0
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items[:safe_limit]):
            if not isinstance(item, dict):
                errors.append({"index": index, "error": "item_must_be_object"})
                continue
            result = self.ingest(item)
            if not result.get("ok"):
                errors.append(
                    {"index": index, "error": str(result.get("error") or "failed")}
                )
                continue
            accepted += 1
            if result.get("created"):
                created += 1
            else:
                updated += 1
        skipped = max(0, len(items) - safe_limit)
        return {
            "ok": not errors,
            "contract_version": CONTRACT_VERSION,
            "accepted": accepted,
            "created": created,
            "updated": updated,
            "failed": len(errors),
            "skipped": skipped,
            "errors": errors[:50],
        }

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        clean_id = self._bounded(evidence_id, 100)
        if not clean_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM warehouse_events WHERE evidence_id=?",
                (clean_id,),
            ).fetchone()
        return self._row(row) if row else None

    def _insert_event(self, conn: sqlite3.Connection, **values: Any) -> int:
        cursor = conn.execute(
            """INSERT INTO warehouse_events
               (evidence_id, external_event_id, scope_id, unified_msg_origin,
                platform, message_type, session_id, group_id, actor_id,
                actor_name, role, event_type, content, content_hash,
                metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["evidence_id"],
                values["external_event_id"],
                values["scope_id"],
                values["origin"],
                values["platform"],
                values["message_type"],
                values["session_id"],
                values["group_id"],
                values["actor_id"],
                values["actor_name"],
                values["role"],
                values["event_type"],
                values["content"],
                values["content_hash"],
                values["metadata_json"],
                values["created_at"],
                values["updated_at"],
            ),
        )
        return int(cursor.lastrowid)

    def _row(self, row: sqlite3.Row, *, snippet: bool = False) -> dict[str, Any]:
        content = str(row["content"] or "")
        return {
            "id": int(row["id"]),
            "evidence_id": str(row["evidence_id"]),
            "external_event_id": str(row["external_event_id"] or ""),
            "scope_id": str(row["scope_id"]),
            "unified_msg_origin": str(row["unified_msg_origin"]),
            "platform": str(row["platform"] or ""),
            "message_type": str(row["message_type"] or ""),
            "session_id": str(row["session_id"] or ""),
            "group_id": str(row["group_id"] or ""),
            "actor_id": str(row["actor_id"]),
            "actor_name": str(row["actor_name"] or ""),
            "role": str(row["role"]),
            "event_type": str(row["event_type"]),
            "content": content[:700] if snippet else content,
            "snippet": content[:240],
            "metadata": json_object(row["metadata_json"]),
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
        }

    def _replace_fts(
        self,
        conn: sqlite3.Connection,
        *,
        row_id: int,
        content: str,
        evidence_id: str,
        scope_id: str,
        role: str,
        event_type: str,
    ) -> None:
        conn.execute("DELETE FROM warehouse_events_fts WHERE rowid=?", (row_id,))
        conn.execute(
            """INSERT INTO warehouse_events_fts
               (rowid, content, evidence_id, scope_id, role, event_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row_id, content, evidence_id, scope_id, role, event_type),
        )

    def _clean_content(self, value: Any) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text[: self.max_content_chars]

    def _bounded(self, value: Any, limit: int) -> str:
        return " ".join(str(value or "").split())[:limit]

    def _safe_int(self, value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    def _content_hash(self, *parts: str) -> str:
        joined = "\x1f".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def _evidence_id(
        self,
        payload: dict[str, Any],
        *,
        scope_id: str,
        origin: str,
        actor_id: str,
        role: str,
        event_type: str,
        external_event_id: str,
        created_at: int,
        content_hash: str,
    ) -> str:
        explicit = clean_evidence_id(payload.get("evidence_id"))
        if explicit:
            return explicit
        if external_event_id:
            seed = self._content_hash("external", scope_id, origin, external_event_id)
        else:
            seed = self._content_hash(
                "event",
                scope_id,
                origin,
                actor_id,
                role,
                event_type,
                str(created_at),
                content_hash,
            )
        return f"wh:{seed[:24]}"

    def _now(self) -> int:
        return int(time.time())

    def _error(self, error: str) -> dict[str, Any]:
        return {
            "ok": False,
            "contract_version": CONTRACT_VERSION,
            "error": error,
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()
