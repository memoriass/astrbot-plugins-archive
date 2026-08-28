from __future__ import annotations

from typing import Any
import json


class AssetLifecycleMixin:
    def record_review_change(
        self, conn: Any, current: dict[str, Any], new_tags: list[str]
    ) -> None:
        if new_tags == current["tags"]:
            return
        conn.execute(
            """INSERT INTO gallery_review_audit
               (asset_ref, before_tags, after_tags, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                current["asset_ref"],
                json.dumps(current["tags"], ensure_ascii=False),
                json.dumps(new_tags, ensure_ascii=False),
                self._now(),
            ),
        )

    def review_audit(self, asset_ref: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM gallery_review_audit WHERE asset_ref=? ORDER BY id",
                (str(asset_ref or "").strip(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def candidate_feedback(
        self,
        *,
        request_id: str,
        asset_ref: str,
        action: str,
        query: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        clean_request_id = str(request_id or "").strip()[:160]
        clean_ref = str(asset_ref or "").strip()[:120]
        clean_action = str(action or "").strip().lower()
        if not clean_request_id or not clean_ref:
            return {"ok": False, "error": "feedback_identity_required"}
        if clean_action not in {"accepted", "skipped", "replaced", "negative"}:
            return {"ok": False, "error": "feedback_action_invalid"}
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM gallery_candidate_feedback WHERE request_id=?",
                (clean_request_id,),
            ).fetchone()
            if existing:
                same = (
                    str(existing["asset_ref"]) == clean_ref
                    and str(existing["action"]) == clean_action
                )
                return {
                    "ok": same,
                    "idempotent_replay": same,
                    "error": "" if same else "feedback_request_conflict",
                }
            asset = conn.execute(
                "SELECT asset_ref FROM gallery_assets WHERE asset_ref=?",
                (clean_ref,),
            ).fetchone()
            if not asset:
                return {"ok": False, "error": "asset_not_found"}
            conn.execute(
                """INSERT INTO gallery_candidate_feedback
                   (request_id, asset_ref, action, query, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    clean_request_id,
                    clean_ref,
                    clean_action,
                    str(query or "")[:500],
                    str(reason or "")[:500],
                    self._now(),
                ),
            )
        return {"ok": True, "idempotent_replay": False}

    def asset_tombstone(self, asset_ref: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gallery_asset_tombstones WHERE asset_ref=?",
                (str(asset_ref or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def reference_status(self, asset_ref: str) -> dict[str, Any]:
        clean_ref = str(asset_ref or "").strip()
        asset = self.get_asset_by_ref(clean_ref)
        if asset:
            return {"ok": True, "status": "active", "asset": asset}
        tombstone = self.asset_tombstone(clean_ref)
        if tombstone:
            return {"ok": True, "status": "deleted", "tombstone": tombstone}
        return {"ok": False, "status": "missing", "error": "asset_ref_not_found"}
