from __future__ import annotations

from time import time

from ..storage import PlanaStorage
from .graph import ConceptGraph
from .models import DecayReport, MemoryRecord
from .tokenizer import SimpleTokenizer


class MemoryDecay:
    def __init__(
        self,
        storage: PlanaStorage,
        batch_size: int,
        min_importance: float = 0.08,
        daily_window_seconds: int = 86400,
        concept_graph: ConceptGraph | None = None,
    ):
        self.storage = storage
        self.batch_size = max(1, batch_size)
        self.min_importance = min(max(min_importance, 0.0), 1.0)
        self.daily_window_seconds = max(3600, daily_window_seconds)
        self.concept_graph = concept_graph
        self._tokenizer = SimpleTokenizer(min_length=2)

    def decay_scope(self, scope_id: str) -> DecayReport:
        report = DecayReport(scope_id=scope_id)
        since_ts = int(time()) - self.daily_window_seconds
        candidates = self.storage.decay_candidates(
            scope_id,
            self.batch_size * 2,
            self.min_importance,
        )
        for memory in candidates:
            if report.processed >= self.batch_size:
                break
            if self.storage.memory_decayed_after(memory.id, since_ts):
                report.skipped += 1
                continue
            new_importance = self._next_importance(memory)
            if new_importance >= memory.importance:
                report.skipped += 1
                continue
            self.storage.update_memory_importance(memory.id, new_importance)
            self.storage.record_memory_decay(
                memory.id,
                memory.importance,
                new_importance,
                self._reason(memory),
            )
            report.processed += 1
            report.decayed += 1
        return report

    def _next_importance(self, memory: MemoryRecord) -> float:
        if self._is_protected(memory):
            return memory.importance
        age_days = max(1.0, (int(time()) - memory.created_at) / 86400)
        factor = 0.97 if age_days < 7 else 0.92
        if memory.kind in {"message", "llm_response"}:
            factor -= 0.03
        # Weight-based anti-decay: slow down decay for memories related to
        # high-weight concepts (similar to NachoBot forget_threshold logic).
        concept_weight = self._max_related_concept_weight(memory)
        if concept_weight >= 3.0:
            # Each unit of weight above 3 adds ~0.01 to the factor,
            # capped so factor never exceeds 0.99.
            bonus = min(0.05, (concept_weight - 3.0) * 0.01)
            factor = min(0.99, factor + bonus)
        return max(self.min_importance, round(memory.importance * factor, 4))

    def _max_related_concept_weight(self, memory: MemoryRecord) -> float:
        """Find the highest concept weight related to this memory."""
        if self.concept_graph is None:
            return 0.0
        terms = self._tokenizer.search_terms(memory.content[:200])
        if not terms:
            return 0.0
        max_weight = 0.0
        for term in terms[:4]:
            node = self.concept_graph.storage.get_node(term.strip().lower()[:120])
            if node is not None and node.weight > max_weight:
                max_weight = node.weight
        return max_weight

    def _is_protected(self, memory: MemoryRecord) -> bool:
        protected_kinds = {"semantic_note", "tool_authorization", "risk_event"}
        if memory.kind in protected_kinds:
            return True
        protected_terms = ("授权", "确认", "风险", "删除", "备份", "credential")
        content = memory.content.lower()
        return any(term in content for term in protected_terms)

    def _reason(self, memory: MemoryRecord) -> str:
        if memory.kind in {"message", "llm_response"}:
            return "routine_event_decay"
        return "low_activity_decay"
