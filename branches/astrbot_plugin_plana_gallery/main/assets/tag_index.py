from __future__ import annotations

from typing import Any


class TagIndexMixin:
    def ensure_tag_index(self, conn: Any) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_asset_tags (
                asset_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY(asset_id, tag),
                FOREIGN KEY(asset_id) REFERENCES gallery_assets(id)
                    ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_asset_tags_tag
                ON gallery_asset_tags(tag, asset_id);
            CREATE INDEX IF NOT EXISTS idx_gallery_asset_tags_asset
                ON gallery_asset_tags(asset_id);
            """
        )
        conn.execute(
            """DELETE FROM gallery_asset_tags
               WHERE asset_id NOT IN (SELECT id FROM gallery_assets)"""
        )
        rows = conn.execute(
            """SELECT a.id, a.tags FROM gallery_assets a
               LEFT JOIN gallery_asset_tags t ON t.asset_id=a.id
               WHERE t.asset_id IS NULL"""
        ).fetchall()
        for row in rows:
            self.replace_asset_tags(conn, int(row["id"]), self._json_list(row["tags"]))

    def replace_asset_tags(self, conn: Any, asset_id: int, tags: list[str]) -> None:
        conn.execute("DELETE FROM gallery_asset_tags WHERE asset_id=?", (asset_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO gallery_asset_tags(asset_id, tag) VALUES (?, ?)",
            [(asset_id, tag) for tag in tags],
        )

    def indexed_tag_counts(self, conn: Any) -> dict[str, int]:
        rows = conn.execute(
            """SELECT tag, COUNT(*) AS count
               FROM gallery_asset_tags
               GROUP BY tag
               ORDER BY tag"""
        ).fetchall()
        return {str(row["tag"]): int(row["count"]) for row in rows}
