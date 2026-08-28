from __future__ import annotations

from typing import Any


class RemoteMappingMixin:
    def list_remote_assets(
        self, provider: str = "", *, limit: int = 200
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        params: list[Any] = []
        where = ""
        if provider:
            where = "WHERE provider=?"
            params.append(provider)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM gallery_remote_assets {where}
                    ORDER BY updated_at DESC LIMIT ?""",  # noqa: S608
                [*params, safe_limit],
            ).fetchall()
        return [_row_to_remote(row) for row in rows]

    def remote_counts(self, provider: str = "") -> dict[str, int]:
        params: list[Any] = []
        where = ""
        if provider:
            where = "WHERE provider=?"
            params.append(provider)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT status, COUNT(*) AS count
                    FROM gallery_remote_assets {where}
                    GROUP BY status""",  # noqa: S608
                params,
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

def _row_to_remote(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "asset_id": int(row["asset_id"]),
        "provider": row["provider"],
        "remote_key": row["remote_key"],
        "remote_url": row["remote_url"],
        "status": row["status"],
        "error": row["error"],
        "uploaded_at": int(row["uploaded_at"]),
        "updated_at": int(row["updated_at"]),
    }
