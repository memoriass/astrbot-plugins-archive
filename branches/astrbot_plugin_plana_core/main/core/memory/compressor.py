from __future__ import annotations

from astrbot.api.provider import Provider

from .graph import ConceptGraph
from .llm_extractor import LLMKeywordExtractor
from .models import MemoryRecord


class MemoryCompressor:
    """Compress episodic memories into concept graph entries.

    Uses LLM keyword extraction and topic summarization to distill
    a batch of memories into concept nodes and edges.
    """

    def __init__(
        self,
        concept_graph: ConceptGraph,
        llm_extractor: LLMKeywordExtractor,
    ):
        self.concept_graph = concept_graph
        self.llm_extractor = llm_extractor

    async def compress(
        self,
        memories: list[MemoryRecord],
        provider: Provider | None,
    ) -> int:
        """Compress a batch of memories into concept graph entries.

        Returns the number of concepts written.
        """
        if not memories or provider is None:
            return 0
        text = self._batch_text(memories)
        if not text:
            return 0
        try:
            keywords = await self.llm_extractor.extract_keywords(text, provider)
        except Exception:  # noqa: BLE001
            return 0
        written = 0
        for kw in keywords:
            summary = await self._safe_summarize(text, kw, provider)
            if not summary:
                summary = text[:200]
            existing = self.concept_graph.storage.get_node(kw.strip().lower()[:120])
            if existing is not None and existing.memory_items.strip():
                merged = await self._safe_integrate(
                    existing.memory_items, summary, provider
                )
                self.concept_graph.add_concept(kw, merged)
            else:
                self.concept_graph.add_concept(kw, summary)
            written += 1
        # Connect extracted keywords as co-occurring concepts.
        for i in range(len(keywords) - 1):
            self.concept_graph.connect_concepts(keywords[i], keywords[i + 1])
        return written

    def _batch_text(self, memories: list[MemoryRecord]) -> str:
        parts = []
        total = 0
        for mem in memories:
            content = mem.content.strip()
            if not content:
                continue
            parts.append(content)
            total += len(content)
            if total > 3000:
                break
        return "\n".join(parts)

    async def _safe_summarize(self, text: str, topic: str, provider: Provider) -> str:
        try:
            return await self.llm_extractor.summarize_topic(text, topic, provider)
        except Exception:  # noqa: BLE001
            return ""

    async def _safe_integrate(self, old: str, new: str, provider: Provider) -> str:
        try:
            return await self.llm_extractor.integrate_memory(old, new, provider)
        except Exception:  # noqa: BLE001
            return f"{old} | {new}"[:4000]
