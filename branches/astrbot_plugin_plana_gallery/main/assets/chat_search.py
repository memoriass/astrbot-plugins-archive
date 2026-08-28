from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from .constants import RESTRICTED_TAG, REVIEW_TAG, SAFE_TAG

_POSITIVE_EMOTIONS = {
    "emotion:happy", "emotion:excited", "emotion:amused", "emotion:affection",
    "emotion:grateful", "emotion:proud", "emotion:relieved", "emotion:comfort",
}
_NEGATIVE_EMOTIONS = {
    "emotion:speechless", "emotion:embarrassed", "emotion:sad",
    "emotion:disappointed", "emotion:angry", "emotion:annoyed",
    "emotion:afraid", "emotion:nervous", "emotion:disgusted", "emotion:tired",
    "emotion:bored",
}


class ChatSearchMixin:
    def chat_candidates(
        self,
        *,
        request_id: str,
        query: str,
        facets: list[str],
        exclude_asset_refs: list[str],
        limit: int,
        emotions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 12))
        clean_query = " ".join(str(query or "").split())[:500]
        clean_facets = self.canonicalize_tags(facets)[:12]
        requested_emotions = self._requested_emotions(emotions or [])
        for item in requested_emotions:
            if item["emotion_tag"] not in clean_facets:
                clean_facets.append(item["emotion_tag"])
        excluded = {str(value or "").strip() for value in exclude_asset_refs[:100]}
        with self._connect() as conn:
            text_ranks = self._fts_ranks(conn, clean_query)
            match_clauses = []
            match_params: list[Any] = []
            if text_ranks:
                match_clauses.append(
                    "a.asset_ref IN ({})".format(",".join("?" for _ in text_ranks))
                )
                match_params.extend(text_ranks)
            if clean_facets:
                match_clauses.append(
                    """a.id IN (SELECT asset_id FROM gallery_asset_tags
                       WHERE tag IN ({}))""".format(",".join("?" for _ in clean_facets))
                )
                match_params.extend(clean_facets)
            match_sql = f"AND ({' OR '.join(match_clauses)})" if match_clauses else ""
            rows = conn.execute(
                f"""SELECT a.* FROM gallery_assets a
                   WHERE a.id IN (
                       SELECT asset_id FROM gallery_asset_tags WHERE tag=?
                   )
                   AND a.id NOT IN (
                       SELECT asset_id FROM gallery_asset_tags WHERE tag IN (?, ?)
                   )
                   {match_sql}
                   ORDER BY a.updated_at DESC LIMIT 1000""",  # noqa: S608
                (SAFE_TAG, REVIEW_TAG, RESTRICTED_TAG, *match_params),
            ).fetchall()
            feedback = self._feedback_scores(conn)
            recent = self._recent_deliveries(conn)
        candidates = []
        for row in rows:
            asset = self._row_to_asset(row)
            asset_ref = str(asset["asset_ref"])
            if asset_ref in excluded or not self._managed_file_valid(asset):
                continue
            tags = set(asset.get("tags", []))
            requested_emotion_tags = {item["emotion_tag"] for item in requested_emotions}
            exact = sum(1 for facet in clean_facets if facet in tags and facet not in requested_emotion_tags)
            if clean_facets and not exact and asset_ref not in text_ranks:
                if not any(item["emotion_tag"] in tags for item in requested_emotions):
                    continue
            emotion_scores = self._emotion_scores(asset.get("emotions", []), requested_emotions)
            score_breakdown = {
                "facet": min(70.0 if not requested_emotions else 35.0, exact * 35.0),
                **emotion_scores,
                "text": text_ranks.get(asset_ref, 0.0),
                "feedback": feedback.get(asset_ref, 0.0),
                "recent_penalty": recent.get(asset_ref, 0.0),
                "diversity": self._stable_jitter(request_id, asset_ref),
            }
            total = sum(score_breakdown.values())
            if not clean_query and not clean_facets:
                total += 10.0
            candidates.append(
                {
                    "asset_id": int(asset["id"]),
                    "asset_ref": asset_ref,
                    "title": str(asset.get("title") or ""),
                    "caption": str(asset.get("caption") or ""),
                    "tags": list(asset.get("tags", [])),
                    "emotions": list(asset.get("emotions", [])),
                    "matched_facets": [tag for tag in clean_facets if tag in tags],
                    "matched_emotions": [
                        item["emotion_tag"] for item in requested_emotions
                        if item["emotion_tag"] in tags
                    ],
                    "score": round(max(0.0, min(100.0, total)), 2),
                    "score_breakdown": {
                        key: round(value, 2) for key, value in score_breakdown.items()
                    },
                    "review_status": "reviewed",
                    "safety": "safe",
                }
            )
        candidates.sort(key=lambda item: (-float(item["score"]), item["asset_ref"]))
        return candidates[:safe_limit]

    def chat_diagnostics(
        self,
        *,
        request_id: str,
        query: str,
        facets: list[str],
        exclude_asset_refs: list[str],
        limit: int,
        emotions: list[dict[str, Any]] | None = None,
        direct_score: float = 50,
        direct_margin: float = 12,
    ) -> dict[str, Any]:
        candidates = self.chat_candidates(
            request_id=request_id,
            query=query,
            facets=facets,
            emotions=emotions,
            exclude_asset_refs=exclude_asset_refs,
            limit=limit,
        )
        excluded_refs = {str(value).strip() for value in exclude_asset_refs}
        exclusions: list[dict[str, str]] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM gallery_assets ORDER BY updated_at DESC LIMIT 2000").fetchall()
        for row in rows:
            asset = self._row_to_asset(row)
            asset_ref = str(asset["asset_ref"])
            tags = set(asset.get("tags", []))
            reason = ""
            if asset_ref in excluded_refs:
                reason = "explicit_exclusion"
            elif REVIEW_TAG in tags:
                reason = "needs_review"
            elif RESTRICTED_TAG in tags:
                reason = "restricted"
            elif SAFE_TAG not in tags:
                reason = "missing_safe_tag"
            elif not self._managed_file_valid(asset):
                reason = "file_invalid"
            if reason:
                exclusions.append({"asset_ref": asset_ref, "reason": reason})
            if len(exclusions) >= 100:
                break
        top = candidates[0] if candidates else None
        second_score = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
        strong = bool(
            top
            and top.get("matched_facets")
            and float(top.get("score") or 0) >= float(direct_score)
            and float(top.get("score") or 0) - second_score >= float(direct_margin)
        )
        return {
            "request_id": request_id[:160],
            "candidates": candidates,
            "exclusions": exclusions,
            "selection_hint": {
                "mode": "direct" if strong else "model_or_none",
                "asset_ref": str(top.get("asset_ref") or "") if strong and top else "",
                "score": float(top.get("score") or 0) if top else 0.0,
                "margin": round(float(top.get("score") or 0) - second_score, 2) if top else 0.0,
            },
        }

    def record_chat_feedback(
        self,
        *,
        event_id: str,
        request_id: str,
        asset_ref: str,
        event: str,
        query: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        clean_event = str(event or "").strip().lower()
        if clean_event not in {"selected", "delivered", "skipped", "negative", "failed"}:
            return {"ok": False, "error": "feedback_event_invalid"}
        clean_request = str(request_id or "").strip()[:160]
        clean_ref = str(asset_ref or "").strip()[:120]
        clean_event_id = str(event_id or "").strip()[:200]
        if not clean_event_id:
            clean_event_id = f"{clean_request}:{clean_event}:{clean_ref}"[:200]
        if not clean_request or not clean_ref:
            return {"ok": False, "error": "feedback_identity_required"}
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM gallery_candidate_events WHERE event_id=?",
                (clean_event_id,),
            ).fetchone()
            if existing:
                same = (
                    str(existing["request_id"]) == clean_request
                    and str(existing["asset_ref"]) == clean_ref
                    and str(existing["event"]) == clean_event
                )
                return {
                    "ok": same,
                    "idempotent_replay": same,
                    "error": "" if same else "feedback_event_conflict",
                }
            asset = conn.execute(
                "SELECT 1 FROM gallery_assets WHERE asset_ref=?", (clean_ref,)
            ).fetchone()
            if not asset:
                return {"ok": False, "error": "asset_not_found"}
            conn.execute(
                """INSERT INTO gallery_candidate_events
                   (event_id, request_id, asset_ref, event, query, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    clean_event_id, clean_request, clean_ref, clean_event,
                    str(query or "")[:500], str(reason or "")[:500], self._now(),
                ),
            )
        return {"ok": True, "idempotent_replay": False, "event_id": clean_event_id}

    def resolve_chat_asset(self, asset_ref: str) -> dict[str, Any]:
        asset = self.get_asset_by_ref(str(asset_ref or "").strip())
        if not asset:
            return {"ok": False, "error": "asset_not_found"}
        tags = set(asset.get("tags", []))
        if REVIEW_TAG in tags:
            return {"ok": False, "error": "asset_not_reviewed"}
        if SAFE_TAG not in tags or RESTRICTED_TAG in tags:
            return {"ok": False, "error": "asset_not_safe"}
        if not self._managed_file_valid(asset):
            return {"ok": False, "error": "asset_file_invalid"}
        path = Path(str(asset["file_path"])).resolve()
        return {
            "ok": True,
            "asset_ref": str(asset["asset_ref"]),
            "file_path": str(path),
            "mime_type": str(asset.get("mime_type") or "application/octet-stream"),
            "title": str(asset.get("title") or ""),
            "caption": str(asset.get("caption") or ""),
        }

    def _fts_ranks(self, conn: Any, query: str) -> dict[str, float]:
        if not query or not self.fts_available:
            return {}
        terms = [term.replace('"', "") for term in query.split() if term.strip()]
        if not terms:
            return {}
        expression = " OR ".join(f'"{term}"' for term in terms[:12])
        try:
            rows = conn.execute(
                """SELECT asset_ref, bm25(gallery_assets_fts) AS rank
                   FROM gallery_assets_fts WHERE gallery_assets_fts MATCH ?
                   ORDER BY rank LIMIT 300""",
                (expression,),
            ).fetchall()
        except Exception:
            return {}
        return {
            str(row["asset_ref"]): min(30.0, 30.0 / (1.0 + abs(float(row["rank"]))))
            for row in rows
        }

    @staticmethod
    def _feedback_scores(conn: Any) -> dict[str, float]:
        rows = conn.execute(
            """SELECT asset_ref,
                      SUM(CASE event WHEN 'delivered' THEN 2 WHEN 'selected' THEN 1
                          WHEN 'negative' THEN -4 WHEN 'failed' THEN -2 ELSE 0 END) AS value
               FROM gallery_candidate_events GROUP BY asset_ref"""
        ).fetchall()
        return {
            str(row["asset_ref"]): max(-20.0, min(15.0, float(row["value"] or 0)))
            for row in rows
        }

    def _recent_deliveries(self, conn: Any) -> dict[str, float]:
        cutoff = self._now() - 7 * 86400
        rows = conn.execute(
            """SELECT asset_ref, COUNT(*) AS count, MAX(created_at) AS last_at
               FROM gallery_candidate_events
               WHERE event='delivered' AND created_at>=? GROUP BY asset_ref""",
            (cutoff,),
        ).fetchall()
        result = {}
        for row in rows:
            age_hours = max(0.0, (self._now() - int(row["last_at"] or 0)) / 3600)
            recency = max(0.0, 12.0 - math.log1p(age_hours) * 3.0)
            result[str(row["asset_ref"])] = -(recency + min(8.0, int(row["count"]) * 1.5))
        return result

    def _managed_file_valid(self, asset: dict[str, Any]) -> bool:
        try:
            root = self.asset_dir.resolve()
            path = Path(str(asset.get("file_path") or "")).resolve()
        except (OSError, RuntimeError):
            return False
        return path.is_file() and (path == root or root in path.parents)

    @staticmethod
    def _stable_jitter(request_id: str, asset_ref: str) -> float:
        digest = hashlib.sha256(f"{request_id}:{asset_ref}".encode("utf-8")).digest()
        return int.from_bytes(digest[:2], "big") / 65535 * 3.0

    def _requested_emotions(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for value in values[:4]:
            if not isinstance(value, dict):
                continue
            raw_tag = str(value.get("emotion_tag") or value.get("tag") or "").strip().lower()
            canonical = self.canonicalize_tags([raw_tag])
            tag = canonical[0] if canonical else raw_tag
            if not tag.startswith("emotion:") or any(item["emotion_tag"] == tag for item in result):
                continue
            try:
                intensity = max(1, min(int(value.get("target_intensity") or value.get("intensity") or 2), 3))
                weight = max(0.1, min(float(value.get("weight") or 1.0), 2.0))
            except (TypeError, ValueError):
                intensity, weight = 2, 1.0
            result.append(
                {
                    "emotion_tag": tag,
                    "target_intensity": intensity,
                    "weight": weight,
                    "prominence": (
                        "primary" if str(value.get("prominence")) == "primary" else "secondary"
                    ),
                }
            )
        return result

    @staticmethod
    def _emotion_scores(
        asset_emotions: list[dict[str, Any]], requested: list[dict[str, Any]]
    ) -> dict[str, float]:
        if not requested:
            return {}
        profiles = {str(item.get("emotion_tag")): item for item in asset_emotions}
        total_weight = sum(float(item["weight"]) for item in requested) or 1.0
        matched_weight = 0.0
        intensity_value = 0.0
        for item in requested:
            profile = profiles.get(str(item["emotion_tag"]))
            if not profile:
                continue
            weight = float(item["weight"])
            matched_weight += weight
            distance = abs(int(profile.get("intensity") or 2) - int(item["target_intensity"]))
            intensity_value += weight * max(0.0, 1.0 - distance / 2.0)
        primary = next(
            (
                item["emotion_tag"]
                for item in requested
                if item.get("prominence") == "primary"
            ),
            requested[0]["emotion_tag"] if requested else "",
        )
        primary_profile = profiles.get(str(primary))
        requested_tags = {str(item["emotion_tag"]) for item in requested}
        primary_group = _emotion_group(str(primary))
        conflict_penalty = 0.0
        if primary_group:
            for profile in asset_emotions:
                tag = str(profile.get("emotion_tag") or "")
                if tag in requested_tags or int(profile.get("intensity") or 2) < 3:
                    continue
                if _emotion_group(tag) and _emotion_group(tag) != primary_group:
                    conflict_penalty -= 12.0
        return {
            "emotion_coverage": 35.0 * matched_weight / total_weight,
            "intensity_match": 20.0 * intensity_value / total_weight,
            "primary_alignment": 10.0 if primary_profile and primary_profile.get("prominence") == "primary" else 0.0,
            "emotion_conflict_penalty": max(-20.0, conflict_penalty),
        }


def _emotion_group(tag: str) -> str:
    if tag in _POSITIVE_EMOTIONS:
        return "positive"
    if tag in _NEGATIVE_EMOTIONS:
        return "negative"
    return ""
