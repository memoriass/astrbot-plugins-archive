from __future__ import annotations

import math
import random
from typing import Any

from .constants import REVIEW_TAG


class AssetQueryMixin:
    def resolve_asset(self, identifier: str) -> dict[str, Any] | None:
        text = str(identifier or "").strip()
        if not text:
            return None
        if text.isdigit():
            return self.get_asset(int(text))
        if text.startswith("gallery:"):
            asset = self.get_asset_by_ref(text)
            if asset:
                return asset
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM gallery_assets
                   WHERE sha256 LIKE ? OR asset_ref LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (f"{text}%", f"{text}%"),
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def list_assets(
        self, *, query: str = "", tag: str = "", limit: int = 50
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        clauses, params = self._asset_filters(query, tag)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM gallery_assets {where}
                    ORDER BY updated_at DESC""",  # noqa: S608
                params,
            ).fetchall()
        return [self._row_to_asset(row) for row in rows[:safe_limit]]

    def list_assets_page(
        self,
        *,
        query: str = "",
        tag: str = "",
        cursor: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
        clauses, params = self._asset_filters(query, tag)
        cursor_parts = str(cursor or "").split(":", 1)
        if len(cursor_parts) == 2 and all(part.isdigit() for part in cursor_parts):
            clauses.append("(updated_at < ? OR (updated_at = ? AND id < ?))")
            updated_at, asset_id = int(cursor_parts[0]), int(cursor_parts[1])
            params.extend([updated_at, updated_at, asset_id])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM gallery_assets {where}
                    ORDER BY updated_at DESC, id DESC LIMIT ?""",  # noqa: S608
                [*params, safe_limit + 1],
            ).fetchall()
        visible = rows[:safe_limit]
        next_cursor = ""
        if len(rows) > safe_limit and visible:
            last = visible[-1]
            next_cursor = f"{int(last['updated_at'])}:{int(last['id'])}"
        return {
            "assets": [self._row_to_asset(row) for row in visible],
            "next_cursor": next_cursor,
        }

    def browse_assets(
        self,
        *,
        query: str = "",
        tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        tag_mode: str = "all",
        review: str = "all",
        source: str = "",
        page: int = 1,
        page_size: int = 48,
        sort: str = "updated_desc",
    ) -> dict[str, Any]:
        safe_page = max(1, int(page))
        safe_page_size = max(12, min(int(page_size), 120))
        clauses, params = self._asset_filters(query, "")
        normalized_tags = self._normalized_filter_tags(tags)
        normalized_excludes = self._normalized_filter_tags(exclude_tags)

        if normalized_tags:
            if str(tag_mode).lower() == "any":
                placeholders = ",".join("?" for _ in normalized_tags)
                clauses.append(
                    f"id IN (SELECT asset_id FROM gallery_asset_tags "
                    f"WHERE tag IN ({placeholders}))"  # noqa: S608
                )
                params.extend(normalized_tags)
            else:
                for selected_tag in normalized_tags:
                    clauses.append(
                        "id IN (SELECT asset_id FROM gallery_asset_tags WHERE tag=?)"
                    )
                    params.append(selected_tag)
        for excluded_tag in normalized_excludes:
            clauses.append(
                "id NOT IN (SELECT asset_id FROM gallery_asset_tags WHERE tag=?)"
            )
            params.append(excluded_tag)

        review_mode = str(review or "all").strip().lower()
        if review_mode == "pending":
            clauses.append(
                "id IN (SELECT asset_id FROM gallery_asset_tags WHERE tag=?)"
            )
            params.append(REVIEW_TAG)
        elif review_mode == "ready":
            clauses.append(
                "id NOT IN (SELECT asset_id FROM gallery_asset_tags WHERE tag=?)"
            )
            params.append(REVIEW_TAG)

        clean_source = str(source or "").strip()[:120]
        if clean_source:
            clauses.append("source=?")
            params.append(clean_source)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_by = {
            "created_desc": "created_at DESC, id DESC",
            "created_asc": "created_at ASC, id ASC",
            "updated_asc": "updated_at ASC, id ASC",
            "title_asc": "title COLLATE NOCASE ASC, id DESC",
            "title_desc": "title COLLATE NOCASE DESC, id DESC",
        }.get(str(sort or "").lower(), "updated_at DESC, id DESC")
        offset = (safe_page - 1) * safe_page_size
        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM gallery_assets {where}",  # noqa: S608
                    params,
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"""SELECT * FROM gallery_assets {where}
                    ORDER BY {order_by} LIMIT ? OFFSET ?""",  # noqa: S608
                [*params, safe_page_size, offset],
            ).fetchall()
            sources = [
                {"source": str(row["source"]), "count": int(row["count"])}
                for row in conn.execute(
                    """SELECT source, COUNT(*) AS count FROM gallery_assets
                       GROUP BY source ORDER BY count DESC, source ASC"""
                ).fetchall()
                if str(row["source"] or "").strip()
            ]
        page_count = max(1, math.ceil(total / safe_page_size)) if total else 1
        return {
            "assets": [self._row_to_asset(row) for row in rows],
            "total": total,
            "page": min(safe_page, page_count),
            "page_size": safe_page_size,
            "page_count": page_count,
            "sources": sources,
        }

    def random_asset(
        self,
        *,
        query: str = "",
        tag: str = "",
        include_review: bool = False,
    ) -> dict[str, Any] | None:
        normalized_tag = str(tag).strip().lower()[:80]
        assets = self.list_assets(query=query, tag=normalized_tag, limit=200)
        if not include_review and normalized_tag != REVIEW_TAG:
            assets = [asset for asset in assets if REVIEW_TAG not in set(asset["tags"])]
        return random.choice(assets) if assets else None

    @staticmethod
    def _asset_filters(query: str, tag: str) -> tuple[list[str], list[Any]]:
        clauses = []
        params: list[Any] = []
        if query:
            clauses.append(
                """(title LIKE ? OR caption LIKE ? OR asset_ref LIKE ?
                    OR id IN (SELECT asset_id FROM gallery_asset_tags WHERE tag LIKE ?))"""
            )
            like = f"%{query[:120]}%"
            params.extend([like, like, like, like])
        if tag:
            clauses.append("id IN (SELECT asset_id FROM gallery_asset_tags WHERE tag=?)")
            params.append(str(tag).strip().lower()[:80])
        return clauses, params

    @staticmethod
    def _normalized_filter_tags(tags: list[str] | None) -> list[str]:
        result = []
        for raw_tag in tags or []:
            tag = str(raw_tag or "").strip().lower()[:80]
            if tag and tag not in result:
                result.append(tag)
        return result[:40]
