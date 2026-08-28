from __future__ import annotations

import json
import sqlite3
from typing import Any

from .constants import (
    DEFAULT_ALIASES,
    DEFAULT_TAGS,
    REVIEW_TAG,
    SAFE_TAG,
)
from .tag_governance import governance_rule_map

SCHEMA_VERSION = 5


class GallerySchemaMixin:
    fts_available = False

    def initialize_local_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gallery_tag_definitions (
                tag TEXT PRIMARY KEY,
                facet TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                managed INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gallery_tag_aliases (
                alias TEXT PRIMARY KEY,
                canonical_tag TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(canonical_tag) REFERENCES gallery_tag_definitions(tag)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_tag_alias_canonical
                ON gallery_tag_aliases(canonical_tag);
            CREATE TABLE IF NOT EXISTS gallery_candidate_events (
                event_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                asset_ref TEXT NOT NULL,
                event TEXT NOT NULL,
                query TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_candidate_events_asset
                ON gallery_candidate_events(asset_ref, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_gallery_candidate_events_request
                ON gallery_candidate_events(request_id, created_at);
            """
        )
        self._seed_tag_taxonomy(conn)
        self._backfill_reviewed_safety(conn)
        try:
            conn.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS gallery_assets_fts USING fts5(
                       asset_ref UNINDEXED, title, caption, tags, aliases
                   )"""
            )
            self.fts_available = True
            self.refresh_search_index(conn)
        except sqlite3.OperationalError:
            self.fts_available = False
        conn.execute(
            """INSERT INTO gallery_schema_meta(key, value) VALUES('schema_version', ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (str(SCHEMA_VERSION),),
        )

    def canonicalize_tags(self, tags: list[str]) -> list[str]:
        normalized: list[str] = []
        with self._connect() as conn:
            aliases = self._alias_map(conn)
        for raw_tag in tags:
            tag = str(raw_tag or "").strip().lower()[:80]
            tag = aliases.get(tag, tag)
            if tag and tag not in normalized:
                normalized.append(tag)
        rules = governance_rule_map()
        first_pass: list[str] = []
        for tag in normalized:
            rule = rules.get(tag)
            replacements = list(rule["targets"]) if rule and bool(rule["auto_apply"]) else [tag]
            for replacement in replacements:
                if replacement not in first_pass:
                    first_pass.append(replacement)
        classified = any(
            tag.startswith(("emotion:", "tone:", "scene:"))
            for tag in first_pass
        )
        result: list[str] = []
        requires_review = False
        for tag in first_pass:
            rule = rules.get(tag)
            if rule and bool(rule["requires_review"]):
                if classified:
                    continue
                requires_review = True
            if tag not in result:
                result.append(tag)
        if requires_review:
            result = [tag for tag in result if tag != SAFE_TAG]
            if REVIEW_TAG not in result:
                result.append(REVIEW_TAG)
        return result[:80]

    def tag_taxonomy(self) -> dict[str, Any]:
        with self._connect() as conn:
            definitions = [
                dict(row)
                for row in conn.execute(
                    """SELECT d.*, COUNT(t.asset_id) AS asset_count
                       FROM gallery_tag_definitions d
                       LEFT JOIN gallery_asset_tags t ON t.tag=d.tag
                       GROUP BY d.tag ORDER BY d.facet, d.tag"""
                ).fetchall()
            ]
            aliases = [
                dict(row)
                for row in conn.execute(
                    "SELECT alias, canonical_tag FROM gallery_tag_aliases ORDER BY alias"
                ).fetchall()
            ]
            orphaned = [
                str(row["tag"])
                for row in conn.execute(
                    """SELECT DISTINCT t.tag FROM gallery_asset_tags t
                       LEFT JOIN gallery_tag_definitions d ON d.tag=t.tag
                       WHERE d.tag IS NULL AND t.tag != ? ORDER BY t.tag""",
                    (REVIEW_TAG,),
                ).fetchall()
            ]
            governance = self.governance_status(conn)
        return {
            "schema_version": SCHEMA_VERSION,
            "definitions": definitions,
            "aliases": aliases,
            "orphaned_tags": orphaned,
            "governance": governance,
            "fts_available": self.fts_available,
        }

    def save_tag_definition(
        self,
        *,
        tag: str,
        label: str = "",
        description: str = "",
        aliases: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_tag = str(tag or "").strip().lower()[:80]
        if not clean_tag or clean_tag == REVIEW_TAG:
            return {"ok": False, "error": "tag_invalid"}
        facet = clean_tag.split(":", 1)[0] if ":" in clean_tag else "custom"
        now = self._now()
        clean_aliases = []
        for value in aliases or []:
            alias = str(value or "").strip().lower()[:80]
            if alias and alias != clean_tag and alias not in clean_aliases:
                clean_aliases.append(alias)
        with self._connect() as conn:
            for alias in clean_aliases:
                canonical_collision = conn.execute(
                    "SELECT tag FROM gallery_tag_definitions WHERE tag=? AND tag!=?",
                    (alias, clean_tag),
                ).fetchone()
                if canonical_collision:
                    return {
                        "ok": False,
                        "error": "alias_conflicts_with_canonical",
                        "alias": alias,
                        "canonical_tag": str(canonical_collision["tag"]),
                    }
                alias_collision = conn.execute(
                    "SELECT canonical_tag FROM gallery_tag_aliases WHERE alias=?",
                    (alias,),
                ).fetchone()
                if alias_collision and str(alias_collision["canonical_tag"]) != clean_tag:
                    return {
                        "ok": False,
                        "error": "alias_conflict",
                        "alias": alias,
                        "canonical_tag": str(alias_collision["canonical_tag"]),
                    }
            conn.execute(
                """INSERT INTO gallery_tag_definitions
                   (tag, facet, label, description, managed, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(tag) DO UPDATE SET
                     facet=excluded.facet, label=excluded.label,
                     description=excluded.description, updated_at=excluded.updated_at""",
                (clean_tag, facet, label[:120], description[:500], now, now),
            )
            conn.execute(
                "DELETE FROM gallery_tag_aliases WHERE canonical_tag=?",
                (clean_tag,),
            )
            conn.executemany(
                """INSERT INTO gallery_tag_aliases(alias, canonical_tag, created_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(alias) DO UPDATE SET canonical_tag=excluded.canonical_tag""",
                [(alias, clean_tag, now) for alias in clean_aliases],
            )
            self.refresh_search_index(conn)
        return {"ok": True, "tag": clean_tag}

    def refresh_search_index(
        self, conn: sqlite3.Connection, asset_id: int | None = None
    ) -> None:
        if not self.fts_available:
            return
        if asset_id is None:
            conn.execute("DELETE FROM gallery_assets_fts")
            rows = conn.execute("SELECT * FROM gallery_assets ORDER BY id").fetchall()
        else:
            row = conn.execute(
                "SELECT * FROM gallery_assets WHERE id=?", (asset_id,)
            ).fetchone()
            rows = [row] if row else []
            if row:
                conn.execute(
                    "DELETE FROM gallery_assets_fts WHERE asset_ref=?",
                    (str(row["asset_ref"]),),
                )
        alias_map = self._alias_map(conn)
        for row in rows:
            tags = self._json_list(row["tags"])
            aliases = [alias for alias, target in alias_map.items() if target in tags]
            conn.execute(
                """INSERT INTO gallery_assets_fts
                   (asset_ref, title, caption, tags, aliases) VALUES (?, ?, ?, ?, ?)""",
                (
                    str(row["asset_ref"]), str(row["title"]), str(row["caption"]),
                    " ".join(tags), " ".join(aliases),
                ),
            )

    def _seed_tag_taxonomy(self, conn: sqlite3.Connection) -> None:
        now = self._now()
        conn.executemany(
            """INSERT INTO gallery_tag_definitions
               (tag, facet, label, description, managed, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)
               ON CONFLICT(tag) DO UPDATE SET
                 facet=CASE WHEN gallery_tag_definitions.managed=1 AND gallery_tag_definitions.facet='' THEN excluded.facet ELSE gallery_tag_definitions.facet END,
                 label=CASE WHEN gallery_tag_definitions.managed=1 AND gallery_tag_definitions.label='' THEN excluded.label ELSE gallery_tag_definitions.label END,
                 description=CASE WHEN gallery_tag_definitions.managed=1 AND gallery_tag_definitions.description='' THEN excluded.description ELSE gallery_tag_definitions.description END,
                 updated_at=CASE WHEN gallery_tag_definitions.managed=1 AND gallery_tag_definitions.description='' THEN excluded.updated_at ELSE gallery_tag_definitions.updated_at END""",
            [(tag, tag.split(":", 1)[0], label, description, now, now) for tag, _, label, description in DEFAULT_TAGS],
        )
        conn.executemany(
            """INSERT OR IGNORE INTO gallery_tag_aliases
               (alias, canonical_tag, created_at) VALUES (?, ?, ?)""",
            [(alias, canonical, now) for alias, canonical in DEFAULT_ALIASES.items()],
        )

    def _backfill_reviewed_safety(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT id, tags FROM gallery_assets").fetchall()
        for row in rows:
            tags = self._json_list(row["tags"])
            if REVIEW_TAG in tags or any(tag.startswith("safety:") for tag in tags):
                continue
            if tags:
                updated_tags = [*tags, SAFE_TAG]
                conn.execute(
                    "UPDATE gallery_assets SET tags=? WHERE id=?",
                    (json.dumps(updated_tags, ensure_ascii=False), int(row["id"])),
                )
                self.replace_asset_tags(conn, int(row["id"]), updated_tags)

    @staticmethod
    def _alias_map(conn: sqlite3.Connection) -> dict[str, str]:
        return {
            str(row["alias"]): str(row["canonical_tag"])
            for row in conn.execute(
                "SELECT alias, canonical_tag FROM gallery_tag_aliases"
            ).fetchall()
        }
