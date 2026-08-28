from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class AssetSerializationMixin:
    def _row_to_asset(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "asset_ref": row["asset_ref"],
            "sha256": row["sha256"],
            "file_path": row["file_path"],
            "original_path": row["original_path"],
            "mime_type": row["mime_type"],
            "title": row["title"],
            "caption": row["caption"],
            "tags": _json_list(row["tags"]),
            "emotions": self.emotions_for_asset(int(row["id"])),
            "source": row["source"],
            "created_at": int(row["created_at"]),
            "updated_at": int(row["updated_at"]),
            "file_valid": Path(str(row["file_path"])).is_file(),
        }


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
