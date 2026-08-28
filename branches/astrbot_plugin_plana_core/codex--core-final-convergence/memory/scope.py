"""Memory scope management for alias resolution and cross-scope migration.

Provides:
- Scope alias mapping: multiple scope_ids can resolve to a canonical scope.
- Incremental migration: copy/move memories between scopes with dedup.
"""

from __future__ import annotations

from time import time
from typing import Any

from ..plugin.db import Database


class ScopeManager:
    """Manages scope aliases and cross-scope memory migration."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scope_aliases (
                    alias TEXT PRIMARY KEY,
                    canonical TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_scope_aliases_canonical
                    ON scope_aliases(canonical);
                """
            )

    def add_alias(self, alias: str, canonical: str) -> bool:
        """Map an alias scope_id to a canonical scope_id."""
        if not alias.strip() or not canonical.strip():
            return False
        if alias == canonical:
            return False
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scope_aliases(alias, canonical, created_at) VALUES (?, ?, ?)",
                (alias.strip(), canonical.strip(), now),
            )
        return True

    def remove_alias(self, alias: str) -> bool:
        """Remove a scope alias."""
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM scope_aliases WHERE alias=?", (alias.strip(),)
            ).rowcount
        return affected > 0

    def resolve(self, scope_id: str) -> str:
        """Resolve a scope_id to its canonical form. Returns input if no alias."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT canonical FROM scope_aliases WHERE alias=?", (scope_id,)
            ).fetchone()
        return row[0] if row else scope_id

    def list_aliases(self, canonical: str | None = None) -> list[dict[str, str]]:
        """List all aliases, optionally filtered by canonical scope."""
        with self.db.connect() as conn:
            if canonical:
                rows = conn.execute(
                    "SELECT alias, canonical, created_at FROM scope_aliases WHERE canonical=? ORDER BY created_at",
                    (canonical,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT alias, canonical, created_at FROM scope_aliases ORDER BY canonical, created_at"
                ).fetchall()
        return [
            {"alias": row[0], "canonical": row[1], "created_at": row[2]} for row in rows
        ]

    def migrate_memories(
        self,
        source_scope: str,
        target_scope: str,
        *,
        limit: int = 100,
        delete_source: bool = False,
    ) -> dict[str, Any]:
        """Migrate episodic memories from source to target scope.

        Deduplicates by content hash. Returns migration stats.
        """
        if source_scope == target_scope:
            return {"error": "same_scope", "migrated": 0}

        safe_limit = max(1, min(limit, 1000))
        migrated = 0
        skipped = 0
        deleted = 0

        with self.db.connect() as conn:
            # Get source memories
            source_rows = conn.execute(
                """SELECT id, kind, content, importance, source, created_at,
                          actor_id, subject
                   FROM episodic_memories WHERE scope_id=?
                   ORDER BY created_at ASC LIMIT ?""",
                (source_scope, safe_limit),
            ).fetchall()

            if not source_rows:
                return {"migrated": 0, "skipped": 0, "deleted": 0, "source_empty": True}

            # Get existing content in target for dedup
            target_contents = set()
            target_rows = conn.execute(
                "SELECT content FROM episodic_memories WHERE scope_id=?",
                (target_scope,),
            ).fetchall()
            for row in target_rows:
                target_contents.add(row[0])

            now = int(time())
            source_ids_migrated = []

            for row in source_rows:
                src_id, kind, content, importance, source, created_at, actor_id, subject = row
                if content in target_contents:
                    skipped += 1
                    if delete_source:
                        source_ids_migrated.append(src_id)
                    continue
                conn.execute(
                    """INSERT INTO episodic_memories(
                           scope, scope_id, kind, content, importance, source,
                           created_at, actor_id, subject
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "session",
                        target_scope,
                        kind,
                        content,
                        importance,
                        f"migrated:{source}",
                        now,
                        actor_id,
                        subject,
                    ),
                )
                migrated += 1
                target_contents.add(content)
                source_ids_migrated.append(src_id)

            if delete_source and source_ids_migrated:
                placeholders = ",".join("?" * len(source_ids_migrated))
                deleted = conn.execute(
                    f"DELETE FROM episodic_memories WHERE id IN ({placeholders})",  # noqa: S608
                    source_ids_migrated,
                ).rowcount

        return {
            "migrated": migrated,
            "skipped": skipped,
            "deleted": deleted,
            "source_total": len(source_rows),
        }
