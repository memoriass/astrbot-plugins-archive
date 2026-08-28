from __future__ import annotations

import sqlite3
from typing import Any


class AssetEmotionMixin:
    def initialize_emotions(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_asset_emotions (
                asset_id INTEGER NOT NULL,
                emotion_tag TEXT NOT NULL,
                intensity INTEGER NOT NULL DEFAULT 2 CHECK(intensity BETWEEN 1 AND 3),
                prominence TEXT NOT NULL DEFAULT 'secondary'
                    CHECK(prominence IN ('primary', 'secondary')),
                source TEXT NOT NULL DEFAULT 'manual',
                suggestion_confidence REAL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(asset_id, emotion_tag),
                FOREIGN KEY(asset_id) REFERENCES gallery_assets(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_asset_emotions_tag
                ON gallery_asset_emotions(emotion_tag, intensity, asset_id);
            CREATE INDEX IF NOT EXISTS idx_gallery_asset_emotions_asset
                ON gallery_asset_emotions(asset_id, prominence);
            """
        )
        self._backfill_emotions(conn)

    def emotions_for_asset(
        self, asset_id: int, conn: sqlite3.Connection | None = None
    ) -> list[dict[str, Any]]:
        if conn is None:
            with self._connect() as active:
                return self.emotions_for_asset(asset_id, active)
        rows = conn.execute(
            """SELECT emotion_tag, intensity, prominence, source,
                      suggestion_confidence, created_at, updated_at
               FROM gallery_asset_emotions WHERE asset_id=?
               ORDER BY CASE prominence WHEN 'primary' THEN 0 ELSE 1 END,
                        intensity DESC, emotion_tag""",
            (int(asset_id),),
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_asset_emotions(
        self,
        conn: sqlite3.Connection,
        asset_id: int,
        tags: list[str],
        emotions: list[dict[str, Any]] | None = None,
        *,
        merge: bool = False,
    ) -> list[dict[str, Any]]:
        emotion_tags = [tag for tag in tags if str(tag).startswith("emotion:")]
        current = self.emotions_for_asset(asset_id, conn)
        if emotions is None:
            normalized = self._normalize_emotions(current, emotion_tags, tags)
        elif merge:
            merged = {str(item["emotion_tag"]): item for item in current}
            for item in emotions:
                merged[str(item.get("emotion_tag") or item.get("tag") or "")] = item
            normalized = self._normalize_emotions(list(merged.values()), emotion_tags, tags)
        else:
            normalized = self._normalize_emotions(emotions, emotion_tags, tags)
        now = self._now()
        conn.execute("DELETE FROM gallery_asset_emotions WHERE asset_id=?", (asset_id,))
        conn.executemany(
            """INSERT INTO gallery_asset_emotions
               (asset_id, emotion_tag, intensity, prominence, source,
                suggestion_confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    asset_id,
                    item["emotion_tag"],
                    item["intensity"],
                    item["prominence"],
                    item["source"],
                    item["suggestion_confidence"],
                    now,
                    now,
                )
                for item in normalized
            ],
        )
        return normalized

    def project_emotion_intensity(
        self, tags: list[str], emotions: list[dict[str, Any]] | None
    ) -> list[str]:
        if emotions is None:
            return tags
        normalized = self._normalize_emotions(
            emotions, [tag for tag in tags if tag.startswith("emotion:")], tags
        )
        result = [tag for tag in tags if not tag.startswith("intensity:")]
        if normalized:
            result.append(f"intensity:{max(item['intensity'] for item in normalized)}")
        return result

    def _normalize_emotions(
        self,
        values: list[dict[str, Any]],
        allowed_tags: list[str],
        tags: list[str],
    ) -> list[dict[str, Any]]:
        allowed = set(allowed_tags)
        global_intensity = next(
            (int(tag.rsplit(":", 1)[1]) for tag in tags if tag in {"intensity:1", "intensity:2", "intensity:3"}),
            2,
        )
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        primary_used = False
        for value in values[:12]:
            if not isinstance(value, dict):
                continue
            raw_tag = str(value.get("emotion_tag") or value.get("tag") or "").strip().lower()
            canonical = self.canonicalize_tags([raw_tag])
            emotion_tag = canonical[0] if canonical else raw_tag
            if emotion_tag not in allowed or emotion_tag in seen:
                continue
            seen.add(emotion_tag)
            try:
                intensity = max(1, min(int(value.get("intensity") or global_intensity), 3))
            except (TypeError, ValueError):
                intensity = global_intensity
            requested_primary = str(value.get("prominence") or "") == "primary"
            prominence = "primary" if requested_primary and not primary_used else "secondary"
            primary_used = primary_used or prominence == "primary"
            confidence = value.get("suggestion_confidence")
            try:
                confidence = max(0.0, min(float(confidence), 1.0)) if confidence is not None else None
            except (TypeError, ValueError):
                confidence = None
            result.append(
                {
                    "emotion_tag": emotion_tag,
                    "intensity": intensity,
                    "prominence": prominence,
                    "source": str(value.get("source") or "manual")[:32],
                    "suggestion_confidence": confidence,
                }
            )
        for emotion_tag in allowed_tags:
            if emotion_tag not in seen:
                result.append(
                    {
                        "emotion_tag": emotion_tag,
                        "intensity": global_intensity,
                        "prominence": "secondary",
                        "source": "compatibility",
                        "suggestion_confidence": None,
                    }
                )
        if result and not any(item["prominence"] == "primary" for item in result):
            result[0]["prominence"] = "primary"
        return result

    def _backfill_emotions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT id, tags FROM gallery_assets ORDER BY id").fetchall()
        for row in rows:
            asset_id = int(row["id"])
            existing = conn.execute(
                "SELECT 1 FROM gallery_asset_emotions WHERE asset_id=? LIMIT 1",
                (asset_id,),
            ).fetchone()
            if existing:
                continue
            tags = self._json_list(row["tags"])
            self.replace_asset_emotions(conn, asset_id, tags)
