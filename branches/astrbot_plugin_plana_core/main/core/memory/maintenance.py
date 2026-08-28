from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MemoryMaintenance:
    """SQLite maintenance helpers for validation, backups and index rebuilds."""

    _EXPECTED_TABLES = (
        "identity_profiles",
        "session_streams",
        "persona_states",
        "episodic_memories",
        "tool_memories",
        "semantic_memories",
        "relation_edges",
        "memory_links",
        "memory_decay_events",
        "task_records",
        "planner_steps",
        "concept_nodes",
        "concept_edges",
        "audit_events",
        "recall_gaps",
        "proactive_tasks",
        "memory_feedback",
        "scope_aliases",
    )

    _INDEXES = (
        (
            "idx_episodic_scope_kind_created",
            "episodic_memories(scope_id, kind, created_at DESC)",
        ),
        (
            "idx_episodic_scope_importance",
            "episodic_memories(scope_id, importance DESC)",
        ),
        ("idx_semantic_scope_subject", "semantic_memories(scope_id, subject)"),
        ("idx_semantic_scope_updated", "semantic_memories(scope_id, updated_at DESC)"),
        ("idx_memory_links_memory", "memory_links(memory_id, target_type)"),
        ("idx_concept_edges_source", "concept_edges(source, strength DESC)"),
        ("idx_concept_edges_target", "concept_edges(target, strength DESC)"),
        ("idx_task_scope_status", "task_records(scope_id, status, updated_at DESC)"),
    )

    def __init__(self, runtime: Any):
        self.runtime = runtime

    @property
    def db_path(self) -> Path:
        return Path(self.runtime.storage.db.db_path)

    @property
    def backup_dir(self) -> Path:
        path = self.db_path.parent / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def validate(self) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        tables = self.runtime.storage.table_counts()
        orphan_links = 0
        orphan_decay = 0
        concept_edge_orphans = 0
        try:
            with self.runtime.storage.db.connect() as conn:
                quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
                existing = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing = [
                    table for table in self._EXPECTED_TABLES if table not in existing
                ]
                if {"memory_links", "episodic_memories"}.issubset(existing):
                    orphan_links = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM memory_links l
                            LEFT JOIN episodic_memories m ON l.memory_id=m.id
                            WHERE m.id IS NULL
                            """
                        ).fetchone()[0]
                    )
                if {"memory_decay_events", "episodic_memories"}.issubset(existing):
                    orphan_decay = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM memory_decay_events d
                            LEFT JOIN episodic_memories m ON d.memory_id=m.id
                            WHERE m.id IS NULL
                            """
                        ).fetchone()[0]
                    )
                if {"concept_edges", "concept_nodes"}.issubset(existing):
                    concept_edge_orphans = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM concept_edges e
                            LEFT JOIN concept_nodes s ON e.source=s.concept
                            LEFT JOIN concept_nodes t ON e.target=t.concept
                            WHERE s.id IS NULL OR t.id IS NULL
                            """
                        ).fetchone()[0]
                    )
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "red",
                "error": str(exc),
                "checks": [{"name": "sqlite", "status": "red", "detail": str(exc)}],
                "tables": tables,
            }

        checks.append(
            {
                "name": "sqlite_quick_check",
                "status": "green" if quick_check == "ok" else "red",
                "detail": quick_check,
            }
        )
        checks.append(
            {
                "name": "schema_tables",
                "status": "green" if not missing else "red",
                "detail": missing,
            }
        )
        checks.append(
            {
                "name": "memory_link_orphans",
                "status": "green" if orphan_links == 0 else "yellow",
                "detail": orphan_links,
            }
        )
        checks.append(
            {
                "name": "decay_event_orphans",
                "status": "green" if orphan_decay == 0 else "yellow",
                "detail": orphan_decay,
            }
        )
        checks.append(
            {
                "name": "concept_edge_orphans",
                "status": "green" if concept_edge_orphans == 0 else "yellow",
                "detail": concept_edge_orphans,
            }
        )
        status = "green"
        if any(item["status"] == "red" for item in checks):
            status = "red"
        elif any(item["status"] == "yellow" for item in checks):
            status = "yellow"
        return {"status": status, "checks": checks, "tables": tables}

    def backup(self, reason: str = "manual") -> dict[str, object]:
        if not self.db_path.exists():
            return {"ok": False, "error": "database_missing", "path": str(self.db_path)}
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        clean_reason = (
            "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:40] or "manual"
        )
        target = self.backup_dir / f"plana-{timestamp}-{clean_reason}.sqlite3"
        try:
            with self.runtime.storage.db.connect() as conn:
                conn.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception:  # noqa: BLE001
            pass
        shutil.copy2(self.db_path, target)
        return {
            "ok": True,
            "path": str(target),
            "size": target.stat().st_size,
            "reason": clean_reason,
        }

    def rebuild_indexes(self) -> dict[str, object]:
        created: list[str] = []
        with self.runtime.storage.db.connect() as conn:
            for name, expression in self._INDEXES:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {expression}")
                created.append(name)
        return {"ok": True, "indexes": created, "count": len(created)}

    def backups(self, limit: int = 8) -> list[dict[str, object]]:
        files = sorted(
            self.backup_dir.glob("plana-*.sqlite3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [
            {
                "name": item.name,
                "path": str(item),
                "size": item.stat().st_size,
                "mtime": int(item.stat().st_mtime),
            }
            for item in files[:limit]
        ]

    def status(self) -> dict[str, object]:
        validation = self.validate()
        return {
            "validation": validation,
            "tables": validation.get("tables", {}),
            "backups": self.backups(),
            "db_path": str(self.db_path),
        }

    def clean_orphans(self, actor: str = "web") -> dict[str, object]:
        """Remove orphan links and decay events, with backup before deletion."""
        validation = self.validate()
        orphan_links = 0
        orphan_decay = 0
        concept_edge_orphans = 0
        for check in validation.get("checks", []):
            if check.get("name") == "memory_link_orphans":
                orphan_links = int(check.get("detail", 0))
            elif check.get("name") == "decay_event_orphans":
                orphan_decay = int(check.get("detail", 0))
            elif check.get("name") == "concept_edge_orphans":
                concept_edge_orphans = int(check.get("detail", 0))
        total = orphan_links + orphan_decay + concept_edge_orphans
        if total == 0:
            return {"ok": True, "cleaned": 0, "detail": "no orphans found"}
        self.backup("before-clean-orphans")
        deleted_links = 0
        deleted_decay = 0
        deleted_edges = 0
        with self.runtime.storage.db.connect() as conn:
            if orphan_links > 0:
                deleted_links = conn.execute(
                    """
                    DELETE FROM memory_links WHERE id IN (
                        SELECT l.id FROM memory_links l
                        LEFT JOIN episodic_memories m ON l.memory_id=m.id
                        WHERE m.id IS NULL
                    )
                    """
                ).rowcount
            if orphan_decay > 0:
                deleted_decay = conn.execute(
                    """
                    DELETE FROM memory_decay_events WHERE id IN (
                        SELECT d.id FROM memory_decay_events d
                        LEFT JOIN episodic_memories m ON d.memory_id=m.id
                        WHERE m.id IS NULL
                    )
                    """
                ).rowcount
            if concept_edge_orphans > 0:
                deleted_edges = conn.execute(
                    """
                    DELETE FROM concept_edges WHERE id IN (
                        SELECT e.id FROM concept_edges e
                        LEFT JOIN concept_nodes s ON e.source=s.concept
                        LEFT JOIN concept_nodes t ON e.target=t.concept
                        WHERE s.id IS NULL OR t.id IS NULL
                    )
                    """
                ).rowcount
        cleaned = deleted_links + deleted_decay + deleted_edges
        audit = self.runtime.memory_storage.audit
        audit.record(
            "clean_orphans",
            "maintenance",
            "",
            f"links={deleted_links} decay={deleted_decay} edges={deleted_edges}",
            actor,
        )
        return {
            "ok": True,
            "cleaned": cleaned,
            "deleted_links": deleted_links,
            "deleted_decay": deleted_decay,
            "deleted_edges": deleted_edges,
        }
