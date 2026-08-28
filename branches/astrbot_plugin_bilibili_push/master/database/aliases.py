from __future__ import annotations

import re
import time


class AliasStoreMixin:
    def upsert_up_alias(
        self,
        *,
        alias: str,
        uid: str,
        username: str = "",
        face: str = "",
        target_id: str = "",
        source: str = "confirmed",
        confidence: float = 1.0,
    ) -> bool:
        normalized = normalize_alias(alias)
        uid = str(uid or "").strip()
        if not normalized or not uid:
            return False
        now = int(time.time())
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT hit_count, created_at
                FROM up_aliases
                WHERE normalized_alias = ? AND uid = ? AND target_id = ?
                """,
                (normalized, uid, str(target_id or "")),
            ).fetchone()
            hit_count = int((existing or [0])[0] or 0)
            created_at = int((existing or [0, now])[1] or now)
            conn.execute(
                """
                INSERT OR REPLACE INTO up_aliases (
                    alias, normalized_alias, uid, username, face, target_id,
                    source, confidence, hit_count, created_at, updated_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(alias).strip(),
                    normalized,
                    uid,
                    str(username or ""),
                    str(face or ""),
                    str(target_id or ""),
                    str(source or "confirmed"),
                    float(confidence),
                    hit_count,
                    created_at,
                    now,
                    now,
                ),
            )
            conn.commit()
            return True

    def find_up_aliases(
        self,
        alias: str,
        *,
        target_id: str = "",
        limit: int = 5,
    ) -> list[dict]:
        normalized = normalize_alias(alias)
        if not normalized:
            return []
        scopes = (str(target_id or ""), "")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT alias, normalized_alias, uid, username, face, target_id,
                       source, confidence, hit_count, created_at, updated_at, last_used_at
                FROM up_aliases
                WHERE normalized_alias = ? AND target_id IN (?, ?)
                ORDER BY CASE WHEN target_id = ? THEN 0 ELSE 1 END,
                         confidence DESC, hit_count DESC, updated_at DESC
                LIMIT ?
                """,
                (normalized, scopes[0], scopes[1], scopes[0], max(1, int(limit))),
            )
            return [self._alias_from_row(row) for row in cursor]

    def upsert_up_alias_evidence(
        self,
        *,
        alias: str,
        uid: str,
        username: str = "",
        face: str = "",
        target_id: str = "",
        source: str = "confirmed",
    ) -> bool:
        normalized = normalize_alias(alias)
        uid = str(uid or "").strip()
        target_id = str(target_id or "").strip()
        if not normalized or not uid or not target_id:
            return False
        now = int(time.time())
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT confirm_count, hit_count, created_at
                FROM up_alias_evidence
                WHERE normalized_alias = ? AND uid = ? AND target_id = ?
                """,
                (normalized, uid, target_id),
            ).fetchone()
            confirm_count = int((existing or [0])[0] or 0) + 1
            hit_count = int((existing or [0, 0])[1] or 0)
            created_at = int((existing or [0, 0, now])[2] or now)
            conn.execute(
                """
                INSERT OR REPLACE INTO up_alias_evidence (
                    alias, normalized_alias, uid, username, face, target_id,
                    source, confirm_count, hit_count, created_at, updated_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(alias).strip(),
                    normalized,
                    uid,
                    str(username or ""),
                    str(face or ""),
                    target_id,
                    str(source or "confirmed"),
                    confirm_count,
                    hit_count,
                    created_at,
                    now,
                    now,
                ),
            )
            conn.commit()
            return True

    def find_shared_up_aliases(
        self,
        alias: str,
        *,
        min_targets: int = 2,
        limit: int = 5,
    ) -> list[dict]:
        normalized = normalize_alias(alias)
        if not normalized:
            return []
        with self._connect() as conn:
            total_uids = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT uid)
                    FROM up_alias_evidence
                    WHERE normalized_alias = ? AND target_id != ''
                    """,
                    (normalized,),
                ).fetchone()[0]
                or 0
            )
            cursor = conn.execute(
                """
                SELECT uid, MAX(alias), MAX(username), MAX(face),
                       COUNT(DISTINCT target_id) AS target_count,
                       SUM(confirm_count) AS confirm_count,
                       SUM(hit_count) AS hit_count,
                       MAX(updated_at) AS updated_at,
                       MAX(last_used_at) AS last_used_at
                FROM up_alias_evidence
                WHERE normalized_alias = ? AND target_id != ''
                GROUP BY uid
                HAVING target_count >= 1
                ORDER BY target_count DESC, confirm_count DESC, hit_count DESC, updated_at DESC
                LIMIT ?
                """,
                (normalized, max(10, int(limit) * 3)),
            )
            rows = [self._shared_alias_from_row(row, normalized) for row in cursor]
        if not rows:
            return []
        for row in rows:
            row["conflict_count"] = max(0, total_uids - 1)
        threshold = max(2, int(min_targets))
        return [row for row in rows if row["target_count"] >= threshold][: max(1, int(limit))]

    def touch_up_alias(self, alias: str, uid: str, target_id: str = "") -> None:
        normalized = normalize_alias(alias)
        if not normalized or not uid:
            return
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE up_aliases
                SET hit_count = hit_count + 1, last_used_at = ?
                WHERE normalized_alias = ? AND uid = ? AND target_id = ?
                """,
                (now, normalized, str(uid), str(target_id or "")),
            )
            conn.commit()

    def touch_up_alias_evidence(self, alias: str, uid: str) -> None:
        normalized = normalize_alias(alias)
        if not normalized or not uid:
            return
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE up_alias_evidence
                SET hit_count = hit_count + 1, last_used_at = ?
                WHERE normalized_alias = ? AND uid = ?
                """,
                (now, normalized, str(uid)),
            )
            conn.commit()

    @staticmethod
    def _alias_from_row(row) -> dict:
        return {
            "alias": str(row[0] or ""),
            "normalized_alias": str(row[1] or ""),
            "uid": str(row[2] or ""),
            "username": str(row[3] or ""),
            "face": str(row[4] or ""),
            "target_id": str(row[5] or ""),
            "source": str(row[6] or ""),
            "confidence": float(row[7] or 0),
            "hit_count": int(row[8] or 0),
            "created_at": int(row[9] or 0),
            "updated_at": int(row[10] or 0),
            "last_used_at": int(row[11] or 0),
        }

    @staticmethod
    def _shared_alias_from_row(row, normalized: str) -> dict:
        return {
            "alias": str(row[1] or ""),
            "normalized_alias": normalized,
            "uid": str(row[0] or ""),
            "username": str(row[2] or ""),
            "face": str(row[3] or ""),
            "target_count": int(row[4] or 0),
            "confirm_count": int(row[5] or 0),
            "hit_count": int(row[6] or 0),
            "updated_at": int(row[7] or 0),
            "last_used_at": int(row[8] or 0),
            "conflict_count": 0,
        }


def normalize_alias(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[\s,，.。!！?？、;；:：()\[\]{}<>《》【】\"'“”‘’]+", "", text)
    return text
