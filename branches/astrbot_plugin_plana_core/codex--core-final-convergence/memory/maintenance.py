from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class MemoryMaintenance:
    """SQLite maintenance helpers for validation, backups and index rebuilds."""

    _EXPECTED_TABLES = (
        "persona_states",
        "episodic_memories",
        "episodic_memories_fts",
        "memory_atoms",
        "memory_atoms_fts",
        "tool_memories",
        "semantic_memories",
        "semantic_memory_history",
        "relation_edges",
        "memory_links",
        "memory_decay_events",
        "concept_nodes",
        "concept_edges",
        "audit_events",
        "recall_gaps",
        "proactive_tasks",
        "memory_feedback",
        "scope_aliases",
        "memory_embeddings",
        "person_info",
        "profile_evidence",
        "profile_snapshots",
        "remote_task_runs",
    )

    _TABLE_CLASSIFICATION = {
        "semantic_memory_history": "audit",
        "identity_profiles": "legacy",
        "session_streams": "legacy",
        "profile_refresh_queue": "legacy",
    }

    _INDEXES = (
        (
            "idx_episodic_scope_kind_created",
            "episodic_memories(scope_id, kind, created_at DESC)",
        ),
        (
            "idx_episodic_scope_importance",
            "episodic_memories(scope_id, importance DESC)",
        ),
        ("idx_episodic_actor", "episodic_memories(actor_id, created_at DESC)"),
        ("idx_episodic_subject", "episodic_memories(subject, created_at DESC)"),
        ("idx_semantic_scope_subject", "semantic_memories(scope_id, subject)"),
        ("idx_semantic_scope_updated", "semantic_memories(scope_id, updated_at DESC)"),
        (
            "idx_semantic_history_key",
            "semantic_memory_history(scope_id, subject, predicate, created_at DESC)",
        ),
        (
            "idx_semantic_history_scope_created",
            "semantic_memory_history(scope_id, created_at DESC)",
        ),
        ("idx_memory_links_memory", "memory_links(memory_id, target_type)"),
        ("idx_memory_atoms_parent", "memory_atoms(parent_memory_id)"),
        ("idx_memory_atoms_scope_status", "memory_atoms(scope_id, status, expires_at)"),
        ("idx_memory_atoms_scope_type", "memory_atoms(scope_id, atom_type, status)"),
        ("idx_memory_atoms_expires", "memory_atoms(status, expires_at)"),
        ("idx_concept_edges_source", "concept_edges(source, strength DESC)"),
        ("idx_concept_edges_target", "concept_edges(target, strength DESC)"),
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
        orphan_atoms = 0
        concept_edge_orphans = 0
        fts_missing = 0
        fts_orphans = 0
        fts_rows = 0
        atom_fts_missing = 0
        atom_fts_orphans = 0
        atom_fts_rows = 0
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
                if {"memory_atoms", "episodic_memories"}.issubset(existing):
                    orphan_atoms = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM memory_atoms a
                            LEFT JOIN episodic_memories m ON a.parent_memory_id=m.id
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
                if {"episodic_memories", "episodic_memories_fts"}.issubset(existing):
                    fts_rows = int(
                        conn.execute(
                            "SELECT COUNT(DISTINCT memory_id) FROM episodic_memories_fts"
                        ).fetchone()[0]
                    )
                    fts_missing = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM episodic_memories m
                            LEFT JOIN episodic_memories_fts f ON f.memory_id=m.id
                            WHERE f.memory_id IS NULL
                            """
                        ).fetchone()[0]
                    )
                    fts_orphans = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM episodic_memories_fts f
                            LEFT JOIN episodic_memories m ON m.id=f.memory_id
                            WHERE m.id IS NULL
                            """
                        ).fetchone()[0]
                    )
                if {"memory_atoms", "memory_atoms_fts"}.issubset(existing):
                    atom_fts_rows = int(
                        conn.execute(
                            "SELECT COUNT(DISTINCT atom_id) FROM memory_atoms_fts"
                        ).fetchone()[0]
                    )
                    atom_fts_missing = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM memory_atoms a
                            LEFT JOIN memory_atoms_fts f ON f.atom_id=a.id
                            WHERE a.status!='forgotten' AND f.atom_id IS NULL
                            """
                        ).fetchone()[0]
                    )
                    atom_fts_orphans = int(
                        conn.execute(
                            """
                            SELECT COUNT(*) FROM memory_atoms_fts f
                            LEFT JOIN memory_atoms a ON a.id=f.atom_id
                            WHERE a.id IS NULL OR a.status='forgotten'
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
                "name": "memory_atom_orphans",
                "status": "green" if orphan_atoms == 0 else "yellow",
                "detail": orphan_atoms,
            }
        )
        checks.append(
            {
                "name": "concept_edge_orphans",
                "status": "green" if concept_edge_orphans == 0 else "yellow",
                "detail": concept_edge_orphans,
            }
        )
        checks.append(
            {
                "name": "episodic_fts_consistency",
                "status": "green" if fts_missing == 0 and fts_orphans == 0 else "yellow",
                "detail": {
                    "indexed": fts_rows,
                    "missing": fts_missing,
                    "orphans": fts_orphans,
                },
            }
        )
        checks.append(
            {
                "name": "memory_atom_fts_consistency",
                "status": "green"
                if atom_fts_missing == 0 and atom_fts_orphans == 0
                else "yellow",
                "detail": {
                    "indexed": atom_fts_rows,
                    "missing": atom_fts_missing,
                    "orphans": atom_fts_orphans,
                },
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
            conn.execute("DELETE FROM episodic_memories_fts")
            conn.execute(
                """
                INSERT INTO episodic_memories_fts(rowid, memory_id, scope_id, kind, content)
                SELECT id, id, scope_id, kind, content
                FROM episodic_memories
                """
            )
            created.append("episodic_memories_fts")
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
            conn.execute("DELETE FROM memory_atoms_fts")
            conn.execute(
                """
                INSERT INTO memory_atoms_fts(rowid, atom_id, scope_id, atom_type, content)
                SELECT id, id, scope_id, atom_type, content
                FROM memory_atoms
                WHERE status!='forgotten'
                """
            )
            created.append("memory_atoms_fts")
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
            "table_classification": dict(self._TABLE_CLASSIFICATION),
        }

    def clean_orphans(self, actor: str = "web") -> dict[str, object]:
        """Remove orphan links and decay events, with backup before deletion."""
        validation = self.validate()
        orphan_links = 0
        orphan_decay = 0
        orphan_atoms = 0
        concept_edge_orphans = 0
        for check in validation.get("checks", []):
            if check.get("name") == "memory_link_orphans":
                orphan_links = int(check.get("detail", 0))
            elif check.get("name") == "decay_event_orphans":
                orphan_decay = int(check.get("detail", 0))
            elif check.get("name") == "memory_atom_orphans":
                orphan_atoms = int(check.get("detail", 0))
            elif check.get("name") == "concept_edge_orphans":
                concept_edge_orphans = int(check.get("detail", 0))
        total = orphan_links + orphan_decay + orphan_atoms + concept_edge_orphans
        if total == 0:
            return {"ok": True, "cleaned": 0, "detail": "no orphans found"}
        self.backup("before-clean-orphans")
        deleted_links = 0
        deleted_decay = 0
        deleted_atoms = 0
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
            if orphan_atoms > 0:
                atom_rows = conn.execute(
                    """
                    SELECT a.id FROM memory_atoms a
                    LEFT JOIN episodic_memories m ON a.parent_memory_id=m.id
                    WHERE m.id IS NULL
                    """
                ).fetchall()
                atom_ids = [int(row[0]) for row in atom_rows]
                if atom_ids:
                    placeholders = ",".join("?" * len(atom_ids))
                    conn.execute(
                        f"DELETE FROM memory_atoms_fts WHERE atom_id IN ({placeholders})",
                        atom_ids,
                    )
                    deleted_atoms = conn.execute(
                        f"DELETE FROM memory_atoms WHERE id IN ({placeholders})",
                        atom_ids,
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
        cleaned = deleted_links + deleted_decay + deleted_atoms + deleted_edges
        audit = self.runtime.memory_storage.audit
        audit.record(
            "clean_orphans",
            "maintenance",
            "",
            f"links={deleted_links} decay={deleted_decay} atoms={deleted_atoms} edges={deleted_edges}",
            actor,
        )
        return {
            "ok": True,
            "cleaned": cleaned,
            "deleted_links": deleted_links,
            "deleted_decay": deleted_decay,
            "deleted_atoms": deleted_atoms,
            "deleted_edges": deleted_edges,
        }
