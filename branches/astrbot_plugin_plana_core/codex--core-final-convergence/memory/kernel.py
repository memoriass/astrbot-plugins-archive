from __future__ import annotations

from typing import Any

from .kernel_context import MemoryKernelContextMixin
from .kernel_profile import MemoryKernelProfileMixin
from .recall_gap_service import RecallGapService


class MemoryKernel(MemoryKernelContextMixin, MemoryKernelProfileMixin):
    """Facade over Plana memory, recall, profile, and maintenance services."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self._last_prompt_context: dict[str, tuple[int, str]] = {}
        self._recall_gap_service = RecallGapService(runtime)

    def search(
        self,
        scope_id: str = "global",
        query: str = "",
        kind: str = "",
        limit: int | float | str | None = None,
    ) -> dict[str, Any]:
        safe_limit = self._limit(limit, self.runtime.recall_default_k, self.runtime.recall_max_k)
        scope = self._scope(scope_id)
        clean_query = str(query or "").strip()
        clean_kind = str(kind or "").strip()
        storage = self.runtime.storage
        if clean_kind and clean_query:
            memories = storage.search_memories_by_kind(scope, clean_query, clean_kind, safe_limit)
        elif clean_kind:
            memories = storage.recent_memories_by_kind(scope, clean_kind, safe_limit)
        elif clean_query:
            memories = storage.search_memories(scope, clean_query, safe_limit)
        else:
            memories = storage.recent_memories(scope, safe_limit)
        semantics = storage.search_semantics(scope, clean_query, safe_limit)
        concepts = self._concepts(clean_query, safe_limit)
        recall = self.runtime.recall_engine.recall(scope, clean_query, clean_kind, safe_limit)
        if clean_query and not recall.get("results"):
            self.runtime.recall_gap_tracker.record_gap(scope, "system", clean_query)
        return {
            "scope": scope,
            "query": clean_query,
            "kind": clean_kind,
            "limit": safe_limit,
            "memories": memories,
            "semantics": semantics,
            "concepts": concepts,
            "results": recall.get("results", []),
            "routes": recall.get("routes", {}),
            "explain": recall.get("explain", {}),
        }

    def ingest_text(
        self,
        scope_id: str,
        user_id: str,
        content: str,
        *,
        kind: str = "semantic_note",
        importance: float = 0.45,
        source: str = "memory_kernel",
        scope: str = "session",
        semantic_predicate: str = "",
        semantic_value: str = "",
        semantic_confidence: float = 0.70,
        actor_id: str = "",
        subject: str = "",
    ) -> dict[str, Any]:
        raw = " ".join(str(content or "").split())
        clean = self._memory_content(raw, 1000)
        if not clean:
            return {"stored": False, "error": "empty_content"}
        resolved_scope = self._scope(scope_id)
        clean_kind = str(kind or "semantic_note")[:80]
        clean_source = str(source or "memory_kernel")[:80]
        memory_id = self.runtime.storage.add_memory(
            str(scope or "session")[:40],
            resolved_scope,
            clean_kind,
            clean,
            self._clamp(importance),
            clean_source,
            actor_id=str(actor_id or user_id or "")[:200],
            subject=str(subject or user_id or "")[:200],
        )
        semantic_written = False
        if semantic_predicate:
            self.runtime.storage.upsert_semantic(
                resolved_scope,
                str(user_id or "unknown")[:160],
                str(semantic_predicate)[:80],
                " ".join(str(semantic_value or clean).split())[:1000],
                self._clamp(semantic_confidence),
                clean_source,
            )
            semantic_written = True
        return {
            "stored": True,
            "scope_id": resolved_scope,
            "kind": clean_kind,
            "content_chars": len(clean),
            "original_chars": len(raw),
            "truncated": len(raw) > len(clean),
            "memory_id": memory_id or 0,
            "semantic_written": semantic_written,
        }

    def ingest_summary(
        self,
        scope_id: str,
        user_id: str,
        summary: str,
        *,
        source: str = "memory_summary",
    ) -> dict[str, Any]:
        return self.ingest_text(
            scope_id,
            user_id,
            summary,
            kind="semantic_note",
            importance=0.55,
            source=source,
            semantic_predicate="summary",
            semantic_confidence=0.72,
        )

    def prompt_context(
        self,
        query: str,
        scope_id: str,
        identity: Any,
        *,
        relations: list[Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        clean_query = " ".join(str(query or "").split())
        active_relations = (relations or [])[: self._runtime_int("max_active_relations", 4)]
        if not bool(getattr(self.runtime, "enable_memory_activation", True)):
            active_context = self._empty_context(active_relations)
            return self._prompt_payload(scope, identity, active_context, "disabled")
        skip_reason = self._cooldown_skip_reason(scope, identity, clean_query, force)
        if skip_reason:
            active_context = self._empty_context(active_relations)
            return self._prompt_payload(scope, identity, active_context, skip_reason)
        active_context = self.runtime.memory_activator.activate(
            clean_query,
            scope,
            identity,
            active_relations,
        )
        active_context = self._bounded_active_context(active_context)
        self._mark_prompt_context(scope, identity, clean_query)
        return self._prompt_payload(scope, identity, active_context, "")

    def stats(self, scope_id: str = "global", user_id: str = "") -> dict[str, Any]:
        scope = self._scope(scope_id)
        return {
            "scope": scope,
            "counts": self.runtime.storage.memory_counts(scope, user_id),
            "recall_gaps": self.runtime.recall_gap_tracker.stats(scope),
            "feedback": self.runtime.feedback_queue.stats(scope),
        }

    def recall_gaps(
        self,
        scope_id: str = "global",
        status: str = "open",
        limit: int | float | str | None = 10,
    ) -> dict[str, Any]:
        return self._recall_gap_service.list_gaps(scope_id, status, limit)

    def propose_recall_gap_memory(
        self,
        scope_id: str,
        gap_id: int | float | str,
        content: str,
        *,
        kind: str = "semantic_note",
        user_id: str = "",
    ) -> dict[str, Any]:
        return self._recall_gap_service.propose_memory(
            scope_id,
            gap_id,
            content,
            kind=kind,
            user_id=user_id,
        )

    def process_memory_feedback(
        self,
        scope_id: str = "global",
        *,
        limit: int | float | str | None = 20,
        actor: str = "memory_feedback",
    ) -> dict[str, Any]:
        return self._recall_gap_service.process_feedback(
            scope_id,
            limit=limit,
            actor=actor,
        )

    def process_memory_feedback_item(
        self,
        scope_id: str,
        feedback_id: int | float | str,
        *,
        actor: str = "memory_feedback",
    ) -> dict[str, Any]:
        return self._recall_gap_service.process_feedback_item(
            scope_id,
            feedback_id,
            actor=actor,
        )

    async def maintain(
        self,
        scope_id: str = "global",
        provider: Any | None = None,
        *,
        consolidate: bool = True,
        decay: bool = True,
        accumulate: bool = False,
        push_warehouse: bool = False,
    ) -> dict[str, Any]:
        scope = self._scope(scope_id)
        results: dict[str, Any] = {"scope": scope}
        consolidation_report = None
        decay_report = None
        if consolidate and self.runtime.enable_memory_consolidation:
            consolidation_report = self.runtime.memory_consolidator.consolidate_scope(
                scope,
                None,
            )
            results["consolidate"] = {
                "processed": consolidation_report.processed,
                "skipped": consolidation_report.skipped,
                "semantic_written": consolidation_report.semantic_written,
            }
        if decay and self.runtime.enable_memory_decay:
            decay_report = self.runtime.memory_decay.decay_scope(scope)
            results["decay"] = {
                "processed": decay_report.processed,
                "decayed": decay_report.decayed,
                "skipped": decay_report.skipped,
                "archived": decay_report.archived,
                "atom_expired": decay_report.atom_expired,
                "atom_forgotten": decay_report.atom_forgotten,
            }
        results["semantic_history"] = self.runtime.storage.prune_semantic_history(
            scope
        )
        if accumulate:
            if provider is None:
                results["accumulate"] = {"skipped": "provider_unavailable"}
            else:
                results["accumulate"] = await self.runtime.memory_accumulator.accumulate(
                    scope,
                    provider,
                )
        if push_warehouse:
            results["warehouse"] = (
                self.runtime.memory_warehouse_pusher.push_maintenance_summary(
                    scope,
                    consolidation_report=consolidation_report,
                    decay_report=decay_report,
                )
            )
        return results
