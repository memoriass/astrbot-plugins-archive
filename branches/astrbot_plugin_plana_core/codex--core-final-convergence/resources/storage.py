from __future__ import annotations

import json
import re
import uuid
from time import time
from typing import Any

from ..plugin.db import Database
from .models import ResourceRecord, ServiceRecord, SubjectRecord
from .workflow_policy import PERMISSIONS

_REF_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,159}$")


class ResourceStorage:
    """Authoritative cross-service resource, binding and delivery registry."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS resource_services (
                    service_ref TEXT PRIMARY KEY,
                    service_type TEXT NOT NULL,
                    execution_target TEXT NOT NULL,
                    credential_ref TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'core',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT 'system',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resources (
                    resource_id TEXT PRIMARY KEY,
                    service_ref TEXT NOT NULL REFERENCES resource_services(service_ref),
                    resource_type TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'adapter',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(service_ref, resource_type, external_id)
                );
                CREATE TABLE IF NOT EXISTS resource_subjects (
                    subject_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    external_id TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(subject_type, platform, external_id)
                );
                CREATE TABLE IF NOT EXISTS resource_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id TEXT NOT NULL REFERENCES resource_subjects(subject_id),
                    resource_id TEXT NOT NULL REFERENCES resources(resource_id),
                    relation_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    source TEXT NOT NULL DEFAULT 'core',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT 'system',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(subject_id, resource_id, relation_type)
                );
                CREATE TABLE IF NOT EXISTS resource_permissions (
                    binding_id INTEGER NOT NULL REFERENCES resource_bindings(id) ON DELETE CASCADE,
                    permission TEXT NOT NULL,
                    effect TEXT NOT NULL DEFAULT 'allow',
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(binding_id, permission)
                );
                CREATE TABLE IF NOT EXISTS resource_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL COLLATE NOCASE,
                    resource_id TEXT NOT NULL REFERENCES resources(resource_id),
                    scope_id TEXT NOT NULL DEFAULT 'global',
                    status TEXT NOT NULL DEFAULT 'candidate',
                    source TEXT NOT NULL DEFAULT 'memory',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(alias, resource_id, scope_id)
                );
                CREATE TABLE IF NOT EXISTS delivery_policies (
                    resource_id TEXT PRIMARY KEY REFERENCES resources(resource_id),
                    group_mode TEXT NOT NULL DEFAULT 'brief',
                    private_mode TEXT NOT NULL DEFAULT 'owner_first',
                    cooldown_seconds INTEGER NOT NULL DEFAULT 600,
                    admin_fallback_subject_id TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_resource_alias_lookup
                    ON resource_aliases(alias, scope_id, status);
                CREATE INDEX IF NOT EXISTS idx_resource_binding_subject
                    ON resource_bindings(subject_id, status);
                """
            )

    def upsert_service(self, record: ServiceRecord, *, actor_id: str = "system") -> None:
        now = int(time())
        service_ref = self._ref(record.service_ref)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO resource_services
                    (service_ref, service_type, execution_target, credential_ref, status,
                     metadata_json, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_ref) DO UPDATE SET
                    service_type=excluded.service_type,
                    execution_target=excluded.execution_target,
                    credential_ref=excluded.credential_ref,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    version=resource_services.version+1,
                    updated_at=excluded.updated_at
                """,
                (service_ref, self._ref(record.service_type), record.execution_target[:120],
                 record.credential_ref[:160], record.status[:32], self._json(record.metadata),
                 actor_id[:160], now, now),
            )

    def upsert_resource(self, record: ResourceRecord, *, source: str = "adapter") -> str:
        now = int(time())
        resource_id = self._ref(record.resource_id or f"res-{uuid.uuid4().hex}")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO resources
                    (resource_id, service_ref, resource_type, external_id, display_name,
                     status, metadata_json, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_ref, resource_type, external_id) DO UPDATE SET
                    display_name=excluded.display_name, status=excluded.status,
                    metadata_json=excluded.metadata_json, source=excluded.source,
                    version=resources.version+1, updated_at=excluded.updated_at
                """,
                (resource_id, self._ref(record.service_ref), self._ref(record.resource_type),
                 record.external_id[:240], record.display_name[:240], record.status[:32],
                 self._json(record.metadata), source[:40], now, now),
            )
            row = conn.execute(
                "SELECT resource_id FROM resources WHERE service_ref=? AND resource_type=? AND external_id=?",
                (record.service_ref, record.resource_type, record.external_id),
            ).fetchone()
        return str(row[0])

    def upsert_subject(self, record: SubjectRecord) -> str:
        now = int(time())
        subject_id = self._ref(record.subject_id or f"sub-{uuid.uuid4().hex}")
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO resource_subjects
                    (subject_id, subject_type, platform, external_id, display_name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject_type, platform, external_id) DO UPDATE SET
                    display_name=excluded.display_name, status=excluded.status, updated_at=excluded.updated_at
                """,
                (subject_id, self._ref(record.subject_type), record.platform[:80],
                 record.external_id[:200], record.display_name[:240], record.status[:32], now, now),
            )
            row = conn.execute(
                "SELECT subject_id FROM resource_subjects WHERE subject_type=? AND platform=? AND external_id=?",
                (record.subject_type, record.platform, record.external_id),
            ).fetchone()
        return str(row[0])

    def bind(
        self, *, subject_id: str, resource_id: str, relation_type: str,
        permissions: set[str], status: str = "candidate", source: str = "core",
        actor_id: str = "system",
    ) -> int:
        invalid = set(permissions) - PERMISSIONS
        if invalid:
            raise ValueError(f"unsupported permissions: {sorted(invalid)}")
        if status not in {"candidate", "active", "disabled", "orphaned"}:
            raise ValueError("invalid binding status")
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO resource_bindings
                    (subject_id, resource_id, relation_type, status, source, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject_id, resource_id, relation_type) DO UPDATE SET
                    status=excluded.status, source=excluded.source,
                    version=resource_bindings.version+1, updated_at=excluded.updated_at
                """,
                (subject_id, resource_id, self._ref(relation_type), status, source[:40], actor_id[:160], now, now),
            )
            row = conn.execute(
                "SELECT id FROM resource_bindings WHERE subject_id=? AND resource_id=? AND relation_type=?",
                (subject_id, resource_id, relation_type),
            ).fetchone()
            binding_id = int(row[0])
            conn.execute("DELETE FROM resource_permissions WHERE binding_id=?", (binding_id,))
            conn.executemany(
                "INSERT INTO resource_permissions(binding_id, permission, created_at) VALUES (?, ?, ?)",
                [(binding_id, permission, now) for permission in sorted(permissions)],
            )
        return binding_id

    def add_alias(
        self, alias: str, resource_id: str, *, scope_id: str = "global",
        status: str = "candidate", source: str = "memory", confidence: float = 0.5,
    ) -> None:
        clean = " ".join(str(alias or "").split())[:160]
        if not clean:
            raise ValueError("alias is required")
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO resource_aliases(alias, resource_id, scope_id, status, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias, resource_id, scope_id) DO UPDATE SET
                    status=excluded.status, source=excluded.source,
                    confidence=excluded.confidence, updated_at=excluded.updated_at
                """,
                (clean, resource_id, scope_id[:200], status, source[:40],
                 max(0.0, min(float(confidence), 1.0)), now, now),
            )

    def resolve_alias(self, alias: str, *, scope_id: str = "global") -> list[dict[str, Any]]:
        clean = " ".join(str(alias or "").split())
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.resource_id, r.service_ref, r.resource_type, r.external_id,
                       r.display_name, r.status, a.confidence, a.scope_id
                FROM resource_aliases a JOIN resources r ON r.resource_id=a.resource_id
                WHERE a.alias=? COLLATE NOCASE AND a.status='active'
                  AND r.status='active' AND a.scope_id IN (?, 'global')
                ORDER BY CASE WHEN a.scope_id=? THEN 0 ELSE 1 END, a.confidence DESC
                """,
                (clean, scope_id, scope_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def authorized_resources(
        self, subject_ids: list[str], *, permission: str,
        service_type: str = "", resource_type: str = "",
    ) -> list[dict[str, Any]]:
        if permission not in PERMISSIONS or not subject_ids:
            return []
        marks = ",".join("?" for _ in subject_ids)
        params: list[Any] = [*subject_ids, permission]
        filters = [f"b.subject_id IN ({marks})", "b.status='active'", "p.permission=?", "p.effect='allow'", "r.status='active'"]
        if service_type:
            filters.append("s.service_type=?")
            params.append(service_type)
        if resource_type:
            filters.append("r.resource_type=?")
            params.append(resource_type)
        query = f"""
            SELECT DISTINCT r.*, s.service_type, b.relation_type, b.subject_id
            FROM resource_bindings b
            JOIN resource_permissions p ON p.binding_id=b.id
            JOIN resources r ON r.resource_id=b.resource_id
            JOIN resource_services s ON s.service_ref=r.service_ref
            WHERE {' AND '.join(filters)} ORDER BY r.display_name
        """
        with self.db.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._resource_row(row) for row in rows]

    def inspection_snapshot(self, *, limit: int = 80) -> dict[str, Any]:
        """Return a bounded read-only snapshot for diagnostics and the dashboard."""

        safe_limit = max(1, min(int(limit or 80), 200))
        with self.db.connect() as conn:
            services = conn.execute(
                """SELECT service_ref, service_type, execution_target, status, source,
                          version, updated_at FROM resource_services
                   ORDER BY updated_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            resources = conn.execute(
                """SELECT r.resource_id, r.service_ref, s.service_type, r.resource_type,
                          r.display_name, r.status, r.source, r.version, r.updated_at
                   FROM resources r JOIN resource_services s ON s.service_ref=r.service_ref
                   ORDER BY r.updated_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            bindings = conn.execute(
                """SELECT b.id, b.subject_id, sub.subject_type, sub.display_name AS subject_name,
                          b.resource_id, r.display_name AS resource_name, b.relation_type,
                          b.status, b.source, b.updated_at,
                          COALESCE(GROUP_CONCAT(p.permission || ':' || p.effect, ', '), '') AS permissions
                   FROM resource_bindings b
                   JOIN resource_subjects sub ON sub.subject_id=b.subject_id
                   JOIN resources r ON r.resource_id=b.resource_id
                   LEFT JOIN resource_permissions p ON p.binding_id=b.id
                   GROUP BY b.id ORDER BY b.updated_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            aliases = conn.execute(
                """SELECT a.id, a.alias, a.scope_id, a.resource_id,
                          r.display_name AS resource_name, a.status, a.source,
                          a.confidence, a.updated_at
                   FROM resource_aliases a JOIN resources r ON r.resource_id=a.resource_id
                   ORDER BY a.updated_at DESC LIMIT ?""",
                (safe_limit,),
            ).fetchall()
            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "resource_services", "resources", "resource_subjects",
                    "resource_bindings", "resource_permissions", "resource_aliases",
                    "delivery_policies",
                )
            }
        return {
            "counts": counts,
            "services": [dict(row) for row in services],
            "resources": [dict(row) for row in resources],
            "bindings": [dict(row) for row in bindings],
            "aliases": [dict(row) for row in aliases],
        }

    def mark_orphaned(self, service_ref: str, live_external_ids: set[str]) -> int:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT resource_id, external_id FROM resources WHERE service_ref=? AND status='active'",
                (service_ref,),
            ).fetchall()
            stale = [str(row[0]) for row in rows if str(row[1]) not in live_external_ids]
            if stale:
                marks = ",".join("?" for _ in stale)
                conn.execute(f"UPDATE resources SET status='orphaned', updated_at=? WHERE resource_id IN ({marks})", (int(time()), *stale))
                conn.execute(f"UPDATE resource_bindings SET status='orphaned', updated_at=? WHERE resource_id IN ({marks})", (int(time()), *stale))
        return len(stale)

    def _resource_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.pop("metadata_json", "{}"))
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data

    def _ref(self, value: str) -> str:
        clean = str(value or "").strip()
        if not _REF_RE.fullmatch(clean):
            raise ValueError(f"invalid resource reference: {clean!r}")
        return clean

    def _json(self, value: Any) -> str:
        return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, separators=(",", ":"))[:16000]
