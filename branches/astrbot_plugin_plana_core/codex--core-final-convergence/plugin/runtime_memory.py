from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..memory import MEMORY_KIND_LLM_RESPONSE, MemoryQueryPlan


class PlanaRuntimeMemoryMixin:
    async def extract_structured_memories(
        self,
        event: AstrMessageEvent,
        response_text: str,
        provider: Any,
    ) -> dict[str, int]:
        if not self.enable_structured_memory_extraction or provider is None:
            return {"items": 0, "episodic_written": 0, "semantic_written": 0}
        identity = self.identity_from_event(event)
        user_text = event.get_message_str().strip()
        memory_scope = self.resolve_scope(event.unified_msg_origin)
        items = await self.structured_extractor.extract(
            user_id=identity.global_user_id,
            nickname=identity.nickname,
            user_text=user_text,
            response_text=response_text,
            provider=provider,
        )
        episodic_written = 0
        semantic_written = 0
        low_quality_items = 0
        source_memory_ids: list[int] = []
        promotable_items = []
        promotable_source_ids: list[int] = []
        for item in items:
            promotable = bool(getattr(item, "promotable", True))
            if not promotable:
                low_quality_items += 1
            written = self.memory_kernel.ingest_text(
                memory_scope,
                item.subject or identity.global_user_id,
                item.content,
                kind=item.kind,
                importance=item.importance,
                source=(
                    "llm_structured_extract"
                    if promotable
                    else "llm_structured_extract_low_quality"
                ),
                actor_id=identity.global_user_id,
                subject=item.subject or f"user:{identity.global_user_id}",
                semantic_predicate=(
                    item.predicate
                    if promotable and item.subject and item.predicate and item.object_value
                    else ""
                ),
                semantic_value=item.object_value,
                semantic_confidence=item.confidence,
            )
            source_memory_id = int(written.get("memory_id") or 0)
            source_memory_ids.append(source_memory_id)
            if promotable:
                promotable_items.append(item)
                promotable_source_ids.append(source_memory_id)
            self.memory_warehouse_pusher.push_structured_memory(
                event,
                scope_id=memory_scope,
                actor_id=identity.global_user_id,
                actor_name=identity.nickname,
                item=item,
                source_memory_id=source_memory_id,
            )
            episodic_written += 1
            if promotable and item.subject and item.predicate and item.object_value:
                semantic_written += 1
        profile_counts = self.profile_scanner.apply(
            memory_scope,
            identity,
            promotable_items,
            raw_text=user_text,
            source_memory_ids=promotable_source_ids,
        )
        snapshot = {}
        if profile_counts.get("profile_written") or profile_counts.get(
            "relation_written"
        ):
            snapshot = self.memory_kernel.capture_person_profile_snapshot(
                memory_scope,
                identity.global_user_id,
                source="structured_memory_extract",
            )
            self.memory_warehouse_pusher.push_profile_snapshot(
                scope_id=memory_scope,
                user_id=identity.global_user_id,
                actor_name=identity.nickname,
                snapshot=snapshot,
            )
        return {
            "items": len(items),
            "episodic_written": episodic_written,
            "semantic_written": semantic_written,
            "low_quality_items": low_quality_items,
            "profile_snapshot": snapshot.get("snapshot_id", 0),
            **profile_counts,
        }

    def _get_relevant_concepts(self, query: str) -> list | None:
        """Retrieve concept nodes relevant to query via spread activation."""
        from ..memory.tokenizer import SimpleTokenizer

        tokenizer = SimpleTokenizer(min_length=2)
        terms = tokenizer.search_terms(query)
        if not terms:
            return None
        activated = self.concept_graph.spread_activation(
            seeds=terms[:6], max_depth=2, top_k=8
        )
        # Also include seed nodes that exist in the graph.
        seed_nodes = []
        for term in terms[:6]:
            node = self.concept_graph.storage.get_node(term.strip().lower()[:120])
            if node is not None:
                seed_nodes.append(node)
        # Merge seed + activated, deduplicate, limit to 8.
        seen = set()
        merged = []
        for node in seed_nodes + activated:
            if node.concept not in seen:
                seen.add(node.concept)
                merged.append(node)
        if not merged:
            return None
        return sorted(merged, key=lambda n: n.weight, reverse=True)[:8]

    async def plan_memory_query(self, text: str, provider) -> MemoryQueryPlan:
        if not self.enable_memory_query_planner:
            return MemoryQueryPlan(False, "", (), "disabled")
        return await self.memory_query_planner.plan(text, provider)

    def record_response(self, event: AstrMessageEvent, text: str) -> None:
        if not self.enabled or not self.record_llm_response or not text.strip():
            return
        identity = self.identity_from_event(event)
        resolved_scope = self.resolve_scope(event.unified_msg_origin)
        try:
            result = self.memory_kernel.ingest_text(
                resolved_scope,
                identity.global_user_id,
                f"Plana response: {text.strip()}",
                kind=MEMORY_KIND_LLM_RESPONSE,
                importance=0.35,
                source="on_llm_response",
                actor_id="plana:core",
                subject=f"user:{identity.global_user_id}",
            )
            if not result.get("stored"):
                logger.warning(
                    "Plana response memory not stored: error=%s scope=%s",
                    result.get("error"),
                    resolved_scope,
                )
            elif self.debug_log:
                logger.debug(
                    "Plana response memory stored: id=%s scope=%s truncated=%s",
                    result.get("memory_id"),
                    resolved_scope,
                    result.get("truncated"),
                )
        except Exception:  # noqa: BLE001
            logger.warning("Plana response memory write failed", exc_info=True)
        self.memory_warehouse_pusher.push_response(event, scope_id=resolved_scope, actor_id="plana:core", actor_name="Plana", content=text)
        # Try to resolve open recall gaps with new response content
        self.recall_gap_tracker.try_resolve_with_content(
            resolved_scope,
            text,
        )

    async def select_concept_nodes_for_prompt(
        self,
        query: str,
        provider,
    ) -> list | None:
        """Two-stage concept selection: spread activation + LLM filtering.

        Returns a list of ConceptNode objects that are relevant to the query,
        or None if concept extraction is disabled or nothing is relevant.
        """
        if not self.enable_concept_extraction or not query.strip():
            return None
        candidates_nodes = self._get_relevant_concepts(query)
        if not candidates_nodes:
            return None
        if provider is None or len(candidates_nodes) <= 3:
            # Skip LLM filtering for small candidate sets.
            return candidates_nodes
        # Build candidate tuples for LLM selection.
        candidate_tuples = [(n.concept, n.memory_items) for n in candidates_nodes]
        try:
            selected_names = await self.llm_extractor.select_relevant_concepts(
                query, candidate_tuples, provider, max_select=4
            )
        except Exception:  # noqa: BLE001
            return candidates_nodes[:4]
        if not selected_names:
            return candidates_nodes[:4]
        name_set = set(selected_names)
        return [
            n for n in candidates_nodes if n.concept in name_set
        ] or candidates_nodes[:4]

    async def extract_and_index_concepts(self, text: str, provider) -> None:
        """Extract concept keywords from text and update the concept graph.

        When a concept already exists, uses LLM to integrate old and new
        memory fragments. Falls back to simple concatenation on failure.
        Silently skips if concept extraction is disabled or provider is None.
        """
        if not self.enable_concept_extraction or not text.strip() or provider is None:
            return
        try:
            keywords = await self.llm_extractor.extract_keywords(text, provider)
            snippet = text[:200]
            for kw in keywords:
                existing = self.concept_graph.storage.get_node(kw.strip().lower()[:120])
                if existing is not None and existing.memory_items.strip():
                    merged = await self.llm_extractor.integrate_memory(
                        existing.memory_items, snippet, provider
                    )
                    self.concept_graph.add_concept(kw, merged)
                else:
                    self.concept_graph.add_concept(kw, snippet)
            for i in range(len(keywords) - 1):
                self.concept_graph.connect_concepts(keywords[i], keywords[i + 1])
        except Exception:  # noqa: BLE001
            pass  # extraction failures must not disrupt message handling

    def _should_record_message(self, text: str) -> bool:
        if not text:
            return False
        # record_all_messages=True: store every user message for richer memory context.
        if self.record_all_messages:
            return True
        # Default: only record messages that explicitly mention Plana.
        return text.startswith("/plana") or "plana" in text.lower() or "普拉娜" in text
