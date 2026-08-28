from __future__ import annotations

from typing import Any


class RecallGapService:
    """Coordinate recall misses, candidate memories, and confirmed feedback."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def list_gaps(
        self,
        scope_id: str = "global",
        status: str = "open",
        limit: int | float | str | None = 10,
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        safe_limit = self._limit(limit, 10, 50)
        safe_status = str(status or "open").strip().lower()
        if safe_status not in {"open", "candidate", "resolved"}:
            safe_status = "open"
        tracker = self.runtime.recall_gap_tracker
        if safe_status == "resolved":
            items = tracker.recent_resolved(scope, safe_limit)
        elif hasattr(tracker, "gaps"):
            items = tracker.gaps(scope, safe_status, safe_limit)
        else:
            items = tracker.open_gaps(scope, safe_limit)
        return {
            "scope": scope,
            "status": safe_status,
            "items": items,
            "stats": tracker.stats(scope),
        }

    def propose_memory(
        self,
        scope_id: str,
        gap_id: int | float | str,
        content: str,
        *,
        kind: str = "semantic_note",
        user_id: str = "",
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        safe_gap_id = self._id(gap_id)
        if safe_gap_id <= 0:
            return {"queued": False, "error": "invalid_gap_id"}
        tracker = self.runtime.recall_gap_tracker
        gap = tracker.get(safe_gap_id) if hasattr(tracker, "get") else None
        if gap is None:
            return {"queued": False, "error": "not_found", "gap_id": safe_gap_id}
        if str(gap.get("scope_id") or "") != scope:
            return {
                "queued": False,
                "error": "scope_mismatch",
                "gap_id": safe_gap_id,
                "gap_scope": gap.get("scope_id"),
                "scope": scope,
            }
        if str(gap.get("status") or "") != "open":
            return {
                "queued": False,
                "error": "gap_not_open",
                "gap": gap,
                "feedback_id": gap.get("candidate_feedback_id"),
            }
        clean = self._clip_text(content, 1000)
        if not clean:
            return {"queued": False, "error": "empty_content", "gap": gap}
        clean_kind = str(kind or "semantic_note").strip()[:50] or "semantic_note"
        actor = str(user_id or gap.get("user_id") or "system")[:200]
        feedback_id = self.runtime.feedback_queue.submit_new_memory(
            scope,
            actor,
            clean,
            clean_kind,
        )
        if feedback_id is None:
            return {"queued": False, "error": "feedback_rejected", "gap": gap}
        marked = tracker.mark_candidate(safe_gap_id, int(feedback_id))
        return {
            "queued": marked,
            "feedback_id": int(feedback_id),
            "gap_id": safe_gap_id,
            "scope": scope,
            "kind": clean_kind,
            "gap": tracker.get(safe_gap_id) if marked and hasattr(tracker, "get") else gap,
            "error": "" if marked else "candidate_mark_failed",
        }

    def process_feedback(
        self,
        scope_id: str = "global",
        *,
        limit: int | float | str | None = 20,
        actor: str = "memory_feedback",
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        safe_limit = self._limit(limit, 20, 50)
        stats = self.runtime.feedback_queue.process_pending(
            self.runtime.storage,
            scope,
            limit=safe_limit,
            actor=actor,
        )
        tracker = self.runtime.recall_gap_tracker
        resolved = (
            tracker.resolve_processed_candidates(scope, safe_limit)
            if hasattr(tracker, "resolve_processed_candidates")
            else []
        )
        return {"scope": scope, "stats": stats, "recall_gap_resolved": resolved}

    def process_feedback_item(
        self,
        scope_id: str,
        feedback_id: int | float | str,
        *,
        actor: str = "memory_feedback",
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        safe_feedback_id = self._id(feedback_id)
        if safe_feedback_id <= 0:
            return {"scope": scope, "ok": False, "error": "invalid_feedback_id"}
        stats = self.runtime.feedback_queue.process_item(
            self.runtime.storage,
            scope,
            safe_feedback_id,
            actor=actor,
        )
        tracker = self.runtime.recall_gap_tracker
        resolved = (
            tracker.resolve_processed_candidates(scope, 1)
            if hasattr(tracker, "resolve_processed_candidates")
            else []
        )
        error = str(stats.get("error") or "")
        if not error and not stats.get("processed"):
            error = "feedback_not_applied"
        return {
            "scope": scope,
            "ok": bool(stats.get("processed")) and not error,
            "error": error,
            "stats": stats,
            "recall_gap_resolved": resolved,
        }

    def _scope(self, scope_id: str) -> str:
        raw = str(scope_id or "global")
        if hasattr(self.runtime, "resolve_scope"):
            return self.runtime.resolve_scope(raw)
        return raw

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        try:
            parsed = int(value if value is not None else default)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, max(1, maximum)))

    @staticmethod
    def _id(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 0
        return max(0, parsed)

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        clean = " ".join(str(text or "").split())
        if limit <= 0:
            return ""
        if limit <= 3:
            return clean[:limit]
        return clean if len(clean) <= limit else clean[: max(0, limit - 3)].rstrip() + "..."
