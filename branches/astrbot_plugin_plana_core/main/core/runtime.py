from __future__ import annotations

import re
from pathlib import Path

from astrbot.api.event import AstrMessageEvent

from .bridge import AronaContract
from .identity.person_info import PersonInfoStorage
from .memory import (
    ALL_MEMORY_KINDS,
    MEMORY_KIND_LLM_RESPONSE,
    MEMORY_KIND_MESSAGE,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_TOOL_RESULT,
    ConceptGraph,
    LLMKeywordExtractor,
    LLMMemoryQueryPlanner,
    LLMStructuredMemoryExtractor,
    MemoryCompressor,
    MemoryQueryPlan,
)
from .memory.accumulator import MemoryAccumulator
from .memory.activator import MemoryActivator
from .memory.consolidator import MemoryConsolidator
from .memory.decay import MemoryDecay
from .memory.embedding import EmbeddingProvider, EmbeddingStore
from .memory.feedback import FeedbackQueue
from .memory.maintenance import MemoryMaintenance
from .memory.recall import PlanaRecallEngine
from .memory.recall_gap import RecallGapTracker
from .memory.scope import ScopeManager
from .models import PlanaState, SessionStream, UserIdentity
from .proactive import ProactiveQueue
from .prompt import PromptBuilder
from .relation import ProfileScanner, RelationGraph
from .safety import SafetyGate
from .storage import PlanaStorage
from .task import RulePlanner, TaskQueue


class PlanaRuntime:
    def __init__(self, data_dir: Path, config):
        self.config = config
        self.enabled = bool(config.get("enabled", True))
        self.mode = str(config.get("mode", "standby"))
        self.inject_prompt = bool(config.get("inject_prompt", True))
        self.record_messages = bool(config.get("record_messages", True))
        self.record_llm_response = bool(config.get("record_llm_response", True))
        self.max_active_memories = int(config.get("max_active_memories", 6))
        self.max_active_semantics = int(config.get("max_active_semantics", 4))
        self.max_active_relations = int(config.get("max_active_relations", 4))
        self.max_prompt_chars = int(config.get("max_prompt_chars", 4000))
        self.enable_relation_graph = bool(config.get("enable_relation_graph", True))
        self.enable_memory_activation = bool(
            config.get("enable_memory_activation", True)
        )
        self.enable_memory_consolidation = bool(
            config.get("enable_memory_consolidation", True)
        )
        self.enable_memory_decay = bool(config.get("enable_memory_decay", True))
        self.consolidation_batch_size = int(config.get("consolidation_batch_size", 12))
        self.decay_batch_size = int(config.get("decay_batch_size", 16))
        self.decay_min_importance = float(config.get("decay_min_importance", 0.08))
        self.enable_task_queue = bool(config.get("enable_task_queue", True))
        self.task_list_limit = int(config.get("task_list_limit", 8))
        self.graph_detail_limit = int(config.get("graph_detail_limit", 8))
        self.enable_concept_extraction = bool(
            config.get("enable_concept_extraction", False)
        )
        self.max_concept_keywords = int(config.get("max_concept_keywords", 4))

        # Configurable persona style — if set, replaces the hard-coded identity block.
        self.persona_style: str = str(config.get("persona_style", ""))
        self.enable_structured_memory_extraction = bool(
            config.get("enable_structured_memory_extraction", True)
        )
        self.structured_memory_max_items = int(
            config.get("structured_memory_max_items", 5)
        )
        self.enable_memory_query_planner = bool(
            config.get("enable_memory_query_planner", True)
        )
        self.enable_recall_tool = bool(config.get("enable_recall_tool", True))
        self.recall_default_k = int(config.get("recall_default_k", 5))
        self.recall_max_k = int(config.get("recall_max_k", 10))
        self.recall_rrf_k = int(config.get("recall_rrf_k", 60))
        self.recall_include_semantic = bool(config.get("recall_include_semantic", True))
        self.recall_include_concept = bool(config.get("recall_include_concept", True))

        # Record ALL user messages (not only Plana-mentioning ones) for better memory.
        self.record_all_messages = bool(config.get("record_all_messages", False))
        # Probability of triggering LLM-based mood_state update per response (0.0 = off).
        self.mood_update_probability: float = float(
            config.get("mood_update_probability", 0.05)
        )

        self.debug_log = bool(config.get("debug_log", False))
        self.accumulate_batch_size = int(config.get("accumulate_batch_size", 8))
        self.arona_contract = AronaContract(bool(config.get("enable_arona_api", False)))
        self.storage = PlanaStorage(data_dir / "plana.sqlite3")
        self.relation_graph = RelationGraph(self.storage)

        self.prompt_builder = PromptBuilder()
        self.concept_graph = ConceptGraph(self.storage.concept_graph_storage)
        self.llm_extractor = LLMKeywordExtractor(max_keywords=self.max_concept_keywords)

        self.memory_activator = MemoryActivator(
            self.storage,
            self.max_active_memories,
            self.max_active_semantics,
            self.max_active_relations,
            concept_graph=(
                self.concept_graph if self.enable_concept_extraction else None
            ),
        )
        self.memory_consolidator = MemoryConsolidator(
            self.storage,
            self.consolidation_batch_size,
        )
        self.memory_decay = MemoryDecay(
            self.storage,
            self.decay_batch_size,
            self.decay_min_importance,
            concept_graph=self.concept_graph,
        )
        self.structured_extractor = LLMStructuredMemoryExtractor(
            self.structured_memory_max_items
        )
        self.memory_query_planner = LLMMemoryQueryPlanner()
        self.profile_scanner = ProfileScanner(self.storage)
        self.maintenance = MemoryMaintenance(self)
        self.recall_gap_tracker = RecallGapTracker(self.storage.db)
        self.proactive_queue = ProactiveQueue(self.storage.db)
        self.feedback_queue = FeedbackQueue(self.storage.db)
        self.scope_manager = ScopeManager(self.storage.db)
        self.embedding_store = EmbeddingStore(self.storage.db)
        self.embedding_provider = EmbeddingProvider(self.embedding_store)
        self.person_info_storage = PersonInfoStorage(self.storage.db)
        self._last_query_embedding: list[float] | None = None
        self.recall_engine = PlanaRecallEngine(
            self,
            rrf_k=self.recall_rrf_k,
            include_semantic=self.recall_include_semantic,
            include_concept=self.recall_include_concept,
            embedding_provider=self.embedding_provider,
        )

        self.memory_compressor = MemoryCompressor(
            self.concept_graph, self.llm_extractor
        )
        self.memory_accumulator = MemoryAccumulator(
            self.storage,
            self.memory_compressor,
            self.accumulate_batch_size,
        )

        self.safety_gate = SafetyGate()
        self.task_queue = TaskQueue(self.storage, self.safety_gate)
        self.planner = RulePlanner(self.storage, self.safety_gate)

    def initialize(self) -> None:
        self.storage.initialize()
        self.recall_gap_tracker.initialize()
        self.proactive_queue.initialize()
        self.feedback_queue.initialize()
        self.scope_manager.initialize()
        self.embedding_store.initialize()
        self.person_info_storage.initialize()
        self.storage.get_state("global", self.mode)

    def resolve_scope(self, scope_id: str) -> str:
        """Resolve a scope_id through alias mapping."""
        return self.scope_manager.resolve(scope_id)

    def identity_from_event(self, event: AstrMessageEvent) -> UserIdentity:
        return UserIdentity(
            platform=event.get_platform_name(),
            platform_user_id=str(event.get_sender_id()),
            nickname=str(event.get_sender_name() or event.get_sender_id()),
            role=str(getattr(event, "role", "user") or "user"),
        )

    def session_from_event(self, event: AstrMessageEvent) -> SessionStream:
        message_type = event.get_message_type()
        return SessionStream(
            unified_msg_origin=event.unified_msg_origin,
            platform=event.get_platform_name(),
            message_type=str(getattr(message_type, "value", message_type)),
            session_id=str(event.get_session_id()),
            group_id=event.get_group_id(),
        )

    def ingest_event(self, event: AstrMessageEvent) -> None:
        if not self.enabled or not self.record_messages:
            return
        identity = self.identity_from_event(event)
        session = self.session_from_event(event)
        self.storage.upsert_identity(identity)
        self.storage.upsert_session(session)
        text = event.get_message_str().strip()
        if self._should_record_message(text):
            self.storage.add_memory(
                "session",
                session.unified_msg_origin,
                MEMORY_KIND_MESSAGE,
                f"{identity.nickname}: {text}",
                0.25,
                "message_event",
            )
        if self.enable_relation_graph:
            self.relation_graph.observe_interaction(
                identity,
                text,
                session.unified_msg_origin,
            )

    def build_prompt_for_event(
        self, event: AstrMessageEvent, query_override: str | None = None
    ) -> str:
        if not self.enabled or not self.inject_prompt:
            return ""
        state = self.storage.get_state("global", self.mode)
        if state.mode == "silent":
            return ""
        identity = self.identity_from_event(event)
        self.storage.upsert_identity(identity)
        query = query_override or event.get_message_str().strip()
        if self.enable_memory_activation:
            relations = []
            if self.enable_relation_graph:
                relations = self.relation_graph.active_relations(
                    identity,
                    self.max_active_relations,
                )
            active_context = self.memory_activator.activate(
                query,
                event.unified_msg_origin,
                identity,
                relations,
            )
        else:
            active_context = self.memory_activator.activate(
                "",
                event.unified_msg_origin,
                identity,
                [],
            )
        # Retrieve concept nodes via spread activation instead of global top-N.
        concept_nodes = None
        if self.enable_concept_extraction and query:
            concept_nodes = self._get_relevant_concepts(query)
        # Gather emotion, person_info, and proactive context for prompt.
        emotion_vec = state.emotion if hasattr(state, "emotion") else None
        person_info_data = None
        person = self.person_info_storage.get(
            identity.global_user_id, event.unified_msg_origin
        )
        if person is None:
            person = self.person_info_storage.get(identity.global_user_id, "global")
        if person:
            person_info_data = person.to_dict()
        proactive_count = self.proactive_queue.pending_count(event.unified_msg_origin)
        return self.prompt_builder.build(
            state,
            identity,
            active_context,
            self.max_prompt_chars,
            concept_nodes=concept_nodes,
            persona_style=self.persona_style,
            emotion=emotion_vec,
            person_info=person_info_data,
            proactive_pending=proactive_count,
        )

    def _get_relevant_concepts(self, query: str) -> list | None:
        """Retrieve concept nodes relevant to query via spread activation."""
        from .memory.tokenizer import SimpleTokenizer

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
        self.storage.add_memory(
            "session",
            event.unified_msg_origin,
            MEMORY_KIND_LLM_RESPONSE,
            f"Plana response: {text.strip()[:800]}",
            0.35,
            "on_llm_response",
        )
        # Try to resolve open recall gaps with new response content
        self.recall_gap_tracker.try_resolve_with_content(event.unified_msg_origin, text)

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

    async def extract_structured_memories(
        self,
        event: AstrMessageEvent,
        response_text: str,
        provider,
    ) -> dict[str, int]:
        if not self.enable_structured_memory_extraction or provider is None:
            return {"items": 0, "episodic_written": 0, "semantic_written": 0}
        identity = self.identity_from_event(event)
        user_text = event.get_message_str().strip()
        items = await self.structured_extractor.extract(
            user_id=identity.global_user_id,
            nickname=identity.nickname,
            user_text=user_text,
            response_text=response_text,
            provider=provider,
        )
        episodic_written = 0
        semantic_written = 0
        for item in items:
            self.storage.add_memory(
                "session",
                event.unified_msg_origin,
                item.kind,
                item.content,
                item.importance,
                "llm_structured_extract",
            )
            episodic_written += 1
            if item.subject and item.predicate and item.object_value:
                self.storage.upsert_semantic(
                    event.unified_msg_origin,
                    item.subject,
                    item.predicate,
                    item.object_value,
                    item.confidence,
                    "llm_structured_extract",
                )
                semantic_written += 1
        profile_counts = self.profile_scanner.apply(
            event.unified_msg_origin,
            identity,
            items,
            raw_text=user_text,
        )
        return {
            "items": len(items),
            "episodic_written": episodic_written,
            "semantic_written": semantic_written,
            **profile_counts,
        }

    def record_tool_result(
        self,
        scope_id: str,
        user_id: str,
        tool_name: str,
        objective: str,
        result_summary: str,
        success: bool,
        risk_level: str = "normal",
        task_id: int = 0,
    ) -> dict[str, int]:
        if not self.enabled:
            return {"tool_written": 0, "episodic_written": 0, "semantic_written": 0}
        clean_result = " ".join(result_summary.replace("\n", " ").split())[:600]
        clean_objective = " ".join(objective.replace("\n", " ").split())[:600]
        self.storage.add_tool_memory(
            task_id,
            user_id,
            tool_name,
            clean_objective,
            clean_result,
            success,
            risk_level,
        )
        content = f"Tool {tool_name} {'succeeded' if success else 'failed'}: {clean_objective} -> {clean_result}"
        self.storage.add_memory(
            "session",
            scope_id,
            MEMORY_KIND_TOOL_RESULT,
            content,
            0.65 if success else 0.75,
            "tool_result",
        )
        self.storage.upsert_semantic(
            scope_id,
            f"tool:{tool_name[:80]}",
            "last_result",
            clean_result or clean_objective,
            0.75,
            "tool_result",
        )
        if risk_level in {"medium", "high"}:
            self.storage.add_memory(
                "session",
                scope_id,
                MEMORY_KIND_RISK_EVENT,
                f"Tool risk {risk_level}: {clean_objective}",
                0.8,
                "tool_result",
            )
            return {"tool_written": 1, "episodic_written": 2, "semantic_written": 1}
        return {"tool_written": 1, "episodic_written": 1, "semantic_written": 1}

    def recall_memory(
        self,
        scope_id: str = "global",
        query: str = "",
        kind: str = "",
        k: int | float | str | None = None,
    ) -> dict[str, object]:
        """Recall long-term memory with lightweight RRF fusion."""
        requested_k = self.recall_default_k if k is None else k
        try:
            safe_k = int(requested_k)
        except (TypeError, ValueError):
            safe_k = self.recall_default_k
        safe_k = max(1, min(safe_k, max(1, self.recall_max_k)))
        result = self.recall_engine.recall(scope_id, query, kind, safe_k)
        # Track recall gaps when no results found
        if query.strip() and not result.get("results"):
            self.recall_gap_tracker.record_gap(scope_id, "system", query)
        return result

    async def auto_accumulate_concepts(self, scope_id: str, provider) -> dict[str, int]:
        """Compress recent memories into concept graph entries.

        Returns a dict with processed / written / skipped counts.
        Silently returns zeros if concept extraction is disabled.
        """
        if not self.enable_concept_extraction or provider is None:
            return {"processed": 0, "written": 0, "skipped": 0}
        try:
            return await self.memory_accumulator.accumulate(scope_id, provider)
        except Exception:  # noqa: BLE001
            return {"processed": 0, "written": 0, "skipped": 0}

    def set_mode(self, mode: str) -> bool:
        valid_modes = {
            "standby",
            "observing",
            "tasking",
            "checking",
            "risk_review",
            "waiting_confirm",
            "reporting",
            "handoff_to_arona",
            "silent",
        }
        if mode not in valid_modes:
            return False
        state = self.storage.get_state("global", self.mode)
        self.storage.set_state(
            "global",
            PlanaState(
                mode=mode,
                focus=state.focus,
                pressure=state.pressure,
                risk_level=state.risk_level,
                mood_state=state.mood_state,
            ),
        )
        self.mode = mode
        return True

    def decay_state(self) -> None:
        """Gently decay pressure and converge focus toward baseline (no LLM).

        Called from the maintenance loop each cycle. Inspired by NachoBot's
        MoodRegressionTask — keeps PlanaState values from drifting permanently.
        Pressure floor: 0.10. Focus baseline: 0.72 (10 % step convergence).
        """
        state = self.storage.get_state("global", self.mode)
        new_pressure = max(0.10, state.pressure - 0.02)
        # Converge focus 10 % of the remaining gap toward 0.72 each cycle.
        new_focus = 0.72 + (state.focus - 0.72) * 0.9
        self.storage.set_state(
            "global",
            PlanaState(
                mode=state.mode,
                focus=new_focus,
                pressure=new_pressure,
                risk_level=state.risk_level,
                mood_state=state.mood_state,
            ),
        )

    async def update_mood_by_response(self, text: str, provider) -> None:
        """Probabilistically update mood_state using LLM (inspired by NachoBot ChatMood).

        With probability ``mood_update_probability`` (default 5 %), sends the
        current mood, last LLM response snippet, and persona style to the LLM
        and asks it to produce a one-sentence mood description.  The result is
        persisted to ``PersonaStorage`` so it survives restarts.
        """
        import random  # stdlib — safe inside async method

        if self.mood_update_probability <= 0.0:
            return
        if random.random() > self.mood_update_probability:
            return
        if provider is None:
            return
        state = self.storage.get_state("global", self.mode)
        persona_hint = self.persona_style.strip() or "冷静、准确、简洁的工具执行人格"
        prompt = (
            f"你当前的情绪状态是：{state.mood_state}\n"
            f"你刚刚回复了用户以下内容（节选）：{text[:300]}\n"
            f"你的人格特点是：{persona_hint}\n"
            "请用一句话（不超过30字）描述你现在的情绪状态，"
            "只输出情绪状态本身，不要输出任何其他内容："
        )
        try:
            response = await provider.text_chat(
                prompt=prompt,
                system_prompt=(
                    "你是一个内部情绪状态生成模块。"
                    "只输出简短的中文情绪描述，不要解释，不要多余文字。"
                ),
            )
            new_mood = str(getattr(response, "completion_text", "") or "").strip()
            if new_mood:
                self.storage.set_state(
                    "global",
                    PlanaState(
                        mode=state.mode,
                        focus=state.focus,
                        pressure=state.pressure,
                        risk_level=state.risk_level,
                        mood_state=new_mood[:120],
                    ),
                )
        except Exception:  # noqa: BLE001
            pass  # Never let mood update crash the response pipeline.

    def concept_text(self, command: str = "") -> str:
        """Return a summary of the concept graph for display."""
        cmd = command.strip().lower()
        node_count = self.concept_graph.storage.count_nodes()
        edge_count = self.concept_graph.storage.count_edges()
        header = f"Plana concept graph:\nnodes={node_count}\nedges={edge_count}"
        if cmd == "detail":
            nodes = sorted(
                self.concept_graph.get_all_concepts(),
                key=lambda n: n.weight,
                reverse=True,
            )[:10]
            if nodes:
                lines = [header, "top nodes:"]
                lines.extend(f"  {n.concept} (w={n.weight:.2f})" for n in nodes)
                return "\n".join(lines)
        return header

    def status_text(self) -> str:
        state = self.storage.get_state("global", self.mode)
        arona_state = "enabled" if self.arona_contract.enabled else "disabled"
        return (
            "Plana Core\n"
            f"enabled={self.enabled}\n"
            f"mode={state.mode}\n"
            f"focus={state.focus:.2f}\n"
            f"pressure={state.pressure:.2f}\n"
            f"risk={state.risk_level}\n"
            f"memory_activation={self.enable_memory_activation}\n"
            f"memory_consolidation={self.enable_memory_consolidation}\n"
            f"memory_decay={self.enable_memory_decay}\n"
            f"task_queue={self.enable_task_queue}\n"
            f"prompt_budget={self.max_prompt_chars}\n"
            f"relation_graph={self.enable_relation_graph}\n"
            f"recall_tool={self.enable_recall_tool}\n"
            f"arona_api={arona_state}"
        )

    def recent_text(self, event: AstrMessageEvent) -> str:
        memories = self.storage.recent_memories(event.unified_msg_origin, 8)
        if not memories:
            return "Plana recent memory: empty"
        lines = ["Plana recent memory:"]
        lines.extend(f"{item.id}. [{item.kind}] {item.content}" for item in memories)
        return "\n".join(lines)

    def search_text(self, event: AstrMessageEvent, query: str) -> str:
        identity = self.identity_from_event(event)
        active_context = self.memory_activator.activate(
            query,
            event.unified_msg_origin,
            identity,
        )
        lines = [f"Plana memory search: {query or '<recent>'}"]
        if active_context.memories:
            lines.append("episodic:")
            lines.extend(
                f"{item.id}. [{item.kind}] {item.content}"
                for item in active_context.memories
            )
        if active_context.semantics:
            lines.append("semantic:")
            lines.extend(
                f"{item.id}. {item.subject} {item.predicate} {item.object_value}"
                for item in active_context.semantics
            )
        if len(lines) == 1:
            return "Plana memory search: empty"
        return "\n".join(lines)

    def remember_text(self, event: AstrMessageEvent, content: str) -> str:
        text = content.strip()
        if not text:
            return "Plana remember: empty"
        identity = self.identity_from_event(event)
        self.storage.upsert_identity(identity)
        self.storage.upsert_semantic(
            event.unified_msg_origin,
            identity.global_user_id,
            "note",
            text,
            0.72,
            "plana_command",
        )
        self.storage.add_memory(
            "session",
            event.unified_msg_origin,
            "semantic_note",
            f"{identity.nickname}: {text}",
            0.45,
            "plana_command",
        )
        return "Plana remember: stored"

    def graph_text(self, event: AstrMessageEvent, command: str = "") -> str:
        identity = self.identity_from_event(event)
        if command.strip().lower() == "detail":
            return self.relation_graph.graph_detail_text(
                identity,
                self.graph_detail_limit,
            )
        return self.relation_graph.graph_text(identity, self.max_active_relations)

    def memory_stats_text(self, event: AstrMessageEvent) -> str:
        identity = self.identity_from_event(event)
        counts = self.storage.memory_counts(
            event.unified_msg_origin, identity.global_user_id
        )
        return (
            "Plana memory stats:\n"
            f"episodic={counts['episodic']}\n"
            f"semantic={counts['semantic']}\n"
            f"tool_user={counts['tool_user']}\n"
            f"decay_events={counts['decay_events']}"
        )

    def debug_status_payload(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "mode": self.storage.get_state("global", self.mode).mode,
            "memory_activation": self.enable_memory_activation,
            "memory_consolidation": self.enable_memory_consolidation,
            "memory_decay": self.enable_memory_decay,
            "task_queue": self.enable_task_queue,
            "prompt_budget": self.max_prompt_chars,
            "relation_graph": self.enable_relation_graph,
            "graph_detail_limit": self.graph_detail_limit,
            "concept_extraction": self.enable_concept_extraction,
            "structured_memory_extraction": self.enable_structured_memory_extraction,
            "memory_query_planner": self.enable_memory_query_planner,
            "recall_tool": self.enable_recall_tool,
            "recall_engine": {
                "default_k": self.recall_default_k,
                "max_k": self.recall_max_k,
                "rrf_k": self.recall_rrf_k,
                "include_semantic": self.recall_include_semantic,
                "include_concept": self.recall_include_concept,
            },
            "memory_kinds": list(ALL_MEMORY_KINDS),
            "maintenance": self.maintenance.status(),
            "concept_nodes": self.concept_graph.storage.count_nodes(),
            "concept_edges": self.concept_graph.storage.count_edges(),
            "recall_gaps": self.recall_gap_tracker.stats("global"),
            "tables": self.storage.table_counts(),
        }

    def consolidate_text(self, event: AstrMessageEvent) -> str:
        if not self.enabled or not self.enable_memory_consolidation:
            return "Plana consolidation: disabled"
        identity = self.identity_from_event(event)
        self.storage.upsert_identity(identity)
        report = self.memory_consolidator.consolidate_scope(
            event.unified_msg_origin,
            identity,
        )
        return (
            "Plana consolidation:\n"
            f"scope={report.scope_id}\n"
            f"processed={report.processed}\n"
            f"skipped={report.skipped}\n"
            f"semantic_written={report.semantic_written}"
        )

    def decay_text(self, event: AstrMessageEvent) -> str:
        if not self.enabled or not self.enable_memory_decay:
            return "Plana memory decay: disabled"
        identity = self.identity_from_event(event)
        self.storage.upsert_identity(identity)
        report = self.memory_decay.decay_scope(event.unified_msg_origin)
        return (
            "Plana memory decay:\n"
            f"scope={report.scope_id}\n"
            f"processed={report.processed}\n"
            f"decayed={report.decayed}\n"
            f"skipped={report.skipped}"
        )

    def task_text(self, event: AstrMessageEvent, command: str) -> str:
        if not self.enabled or not self.enable_task_queue:
            return "Plana task queue: disabled"
        identity = self.identity_from_event(event)
        self.storage.upsert_identity(identity)
        verb, _, payload = command.partition(" ")
        verb = verb.strip().lower() or "list"
        payload = payload.strip()
        if verb == "list":
            return self._task_list_text(event.unified_msg_origin)
        if verb == "add":
            return self._task_add_text(event, identity.global_user_id, payload)
        if verb in {"done", "cancel"}:
            return self._task_update_text(event, identity.global_user_id, verb, payload)
        return "Plana task commands: list | add <objective> | done <id> | cancel <id>"

    def _task_list_text(self, scope_id: str) -> str:
        tasks = self.task_queue.list(scope_id, self.task_list_limit)
        if not tasks:
            return "Plana tasks: empty"
        lines = ["Plana tasks:"]
        lines.extend(
            f"{task.id}. [{task.status}/{task.risk_level}] {task.objective}"
            for task in tasks
        )
        return "\n".join(lines)

    def _task_add_text(
        self,
        event: AstrMessageEvent,
        owner_id: str,
        objective: str,
    ) -> str:
        task = self.task_queue.add(event.unified_msg_origin, owner_id, objective)
        if task is None:
            return "Plana task add: empty"
        steps = self.planner.plan_for_task(task)
        self.storage.add_memory(
            "session",
            event.unified_msg_origin,
            MEMORY_KIND_TASK_FACT,
            f"task#{task.id} {task.status}/{task.risk_level}: {task.objective}",
            0.50 if task.risk_level == "normal" else 0.65,
            "task_queue",
        )
        lines = [
            "Plana task added:",
            f"id={task.id}",
            f"status={task.status}",
            f"risk={task.risk_level}",
            f"objective={task.objective}",
        ]
        lines.extend(f"step{step.step_index}={step.instruction}" for step in steps)
        return "\n".join(lines)

    def _task_update_text(
        self,
        event: AstrMessageEvent,
        owner_id: str,
        verb: str,
        payload: str,
    ) -> str:
        try:
            task_id = int(payload.strip())
        except ValueError:
            return f"Plana task {verb}: id required"
        if verb == "done":
            task = self.task_queue.done(event.unified_msg_origin, task_id)
        else:
            task = self.task_queue.cancel(event.unified_msg_origin, task_id)
        if task is None:
            return f"Plana task {verb}: not found"
        result_summary = f"task#{task.id} {task.status}/{task.risk_level}"
        self.record_tool_result(
            event.unified_msg_origin,
            owner_id,
            "plana_task_queue",
            self._sanitize_task_text(task.objective),
            result_summary,
            verb == "done",
            task.risk_level,
            task.id,
        )
        self.storage.add_memory(
            "session",
            event.unified_msg_origin,
            MEMORY_KIND_TASK_FACT,
            f"{result_summary}: {self._sanitize_task_text(task.objective)}",
            0.48 if verb == "done" else 0.38,
            "task_queue",
        )
        return (
            f"Plana task {verb}:\n"
            f"id={task.id}\n"
            f"status={task.status}\n"
            f"risk={task.risk_level}\n"
            f"objective={task.objective}"
        )

    def _sanitize_task_text(self, text: str) -> str:
        sanitized = re.sub(
            r"(?i)(token|password|credential|secret|key)=\S+",
            r"\1=<redacted>",
            text,
        )
        sanitized = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1<redacted>",
            sanitized,
        )
        sanitized = re.sub(r"([A-Za-z]:\\[^ \t]+|/[^\s]+)", "<path>", sanitized)

        return sanitized[:600]

    def _should_record_message(self, text: str) -> bool:
        if not text:
            return False
        # record_all_messages=True: store every user message for richer memory context.
        if self.record_all_messages:
            return True
        # Default: only record messages that explicitly mention Plana.
        return text.startswith("/plana") or "plana" in text.lower() or "普拉娜" in text
