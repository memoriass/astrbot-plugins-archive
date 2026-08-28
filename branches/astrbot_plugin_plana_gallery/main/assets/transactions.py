from __future__ import annotations

import json
from typing import Any

from .constants import RESTRICTED_TAG, REVIEW_TAG, SAFE_TAG
PROTECTED_TAGS = {REVIEW_TAG, SAFE_TAG, RESTRICTED_TAG}


class GalleryTransactionMixin:
    def review_commit(
        self,
        changes: list[dict[str, Any]],
        *,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
        emotion_profiles: list[dict[str, Any]] | None = None,
        approve: bool = False,
    ) -> dict[str, Any]:
        if not changes:
            return {"ok": False, "error": "missing_changes"}
        shared_add = _clean_tags(add_tags or [])
        shared_remove = set(_clean_tags(remove_tags or []))
        shared_emotions = _clean_emotions(emotion_profiles or [])
        if _contains_protected(shared_add) or _contains_protected(shared_remove):
            return {"ok": False, "error": "protected_tag"}
        try:
            with self._connect() as conn:
                aliases = self._alias_map(conn)
                updated: list[dict[str, Any]] = []
                for change in changes[:200]:
                    asset_id = int(change.get("id") or 0)
                    row = conn.execute(
                        "SELECT * FROM gallery_assets WHERE id=?", (asset_id,)
                    ).fetchone()
                    if not row:
                        raise _TransactionError("not_found", asset_id)
                    expected = int(change.get("expected_updated_at") or 0)
                    if expected and expected != int(row["updated_at"]):
                        raise _TransactionError("version_conflict", asset_id)
                    current = self._row_to_asset(row)
                    item_add = _clean_tags(change.get("add_tags") or [])
                    item_remove = set(_clean_tags(change.get("remove_tags") or []))
                    if _contains_protected(item_add) or _contains_protected(item_remove):
                        raise _TransactionError("protected_tag", asset_id)
                    tags = [tag for tag in current["tags"] if tag not in shared_remove | item_remove]
                    for raw_tag in [*shared_add, *item_add]:
                        tag = aliases.get(raw_tag, raw_tag)
                        if tag and tag not in tags:
                            tags.append(tag)
                    emotion_map = {
                        str(item["emotion_tag"]): item
                        for item in current.get("emotions", [])
                    }
                    for item in [*shared_emotions, *_clean_emotions(change.get("emotions") or [])]:
                        emotion_map[str(item["emotion_tag"])] = item
                    if approve:
                        if not self._managed_file_valid(current):
                            raise _TransactionError("asset_file_invalid", asset_id)
                        if RESTRICTED_TAG in tags:
                            raise _TransactionError("restricted_asset", asset_id)
                        tags = [tag for tag in tags if tag not in {REVIEW_TAG, SAFE_TAG}]
                        tags.append(SAFE_TAG)
                    if not tags:
                        raise _TransactionError("missing_tags", asset_id)
                    emotions = list(emotion_map.values())
                    tags = self.project_emotion_intensity(tags, emotions)
                    updated_at = max(self._now(), int(row["updated_at"]) + 1)
                    conn.execute(
                        "UPDATE gallery_assets SET tags=?, updated_at=? WHERE id=?",
                        (json.dumps(tags, ensure_ascii=False), updated_at, asset_id),
                    )
                    self.replace_asset_tags(conn, asset_id, tags)
                    self.replace_asset_emotions(conn, asset_id, tags, emotions)
                    self.record_review_change(conn, current, tags)
                    self.refresh_search_index(conn, asset_id)
                    next_row = conn.execute(
                        "SELECT * FROM gallery_assets WHERE id=?", (asset_id,)
                    ).fetchone()
                    updated.append(self._row_to_asset(next_row))
        except _TransactionError as exc:
            return {"ok": False, "error": exc.code, "asset_id": exc.asset_id}
        return {"ok": True, "count": len(updated), "updated": updated}


class _TransactionError(Exception):
    def __init__(self, code: str, asset_id: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.asset_id = asset_id


def _clean_tags(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values[:100]:
        tag = str(value or "").strip().lower()[:80]
        if tag and tag not in result:
            result.append(tag)
    return result

def _contains_protected(values: Any) -> bool:
    return any(str(value) in PROTECTED_TAGS or str(value).startswith("safety:") for value in values)


def _clean_emotions(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    for value in values[:12]:
        if not isinstance(value, dict):
            continue
        tag = str(value.get("emotion_tag") or value.get("tag") or "").strip().lower()[:80]
        if not tag.startswith("emotion:"):
            continue
        try:
            intensity = max(1, min(int(value.get("intensity") or 2), 3))
        except (TypeError, ValueError):
            intensity = 2
        result.append(
            {
                "emotion_tag": tag,
                "intensity": intensity,
                "prominence": "primary" if str(value.get("prominence")) == "primary" else "secondary",
                "source": str(value.get("source") or "manual")[:32],
                "suggestion_confidence": value.get("suggestion_confidence"),
            }
        )
    return result
