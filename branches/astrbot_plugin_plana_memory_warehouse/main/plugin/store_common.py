from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

CONTRACT_VERSION = "plana.memory_warehouse.v1"
DEFAULT_BULK_LIMIT = 1000


def bounded_metadata(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:60]:
        clean_key = str(key or "").strip()[:80]
        if not clean_key:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[clean_key] = str(item)[:700] if isinstance(item, str) else item
        elif isinstance(item, list):
            result[clean_key] = [str(part)[:180] for part in item[:30]]
        else:
            result[clean_key] = str(item)[:700]
    return result


def json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def clean_evidence_id(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"wh:[A-Za-z0-9_.:-]{8,100}", text):
        return text[:100]
    return ""


def query_terms(query: str) -> list[str]:
    terms = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    return [term for term in terms if term][:8]


def fts_query(query: str) -> str:
    return " OR ".join(f'"{term}"' for term in query_terms(query))


def like_pattern(query: str) -> str:
    escaped = (
        str(query or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def merge_rows(
    primary: list[sqlite3.Row],
    fallback: list[sqlite3.Row],
    limit: int,
) -> list[sqlite3.Row]:
    seen = {int(row["id"]) for row in primary}
    merged = list(primary)
    for row in fallback:
        row_id = int(row["id"])
        if row_id in seen:
            continue
        seen.add(row_id)
        merged.append(row)
        if len(merged) >= limit:
            break
    return merged[:limit]


_like_pattern = like_pattern
