from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..bridge import BridgeContract
from ..identity.person_info import PersonInfoStorage
from ..identity.profile_evidence import ProfileEvidenceStorage
from ..jobs import RuntimeJobManager
from ..memory import (
    MEMORY_KIND_MESSAGE,
    ConceptGraph,
    LLMKeywordExtractor,
    LLMMemoryQueryPlanner,
    LLMStructuredMemoryExtractor,
    MemoryCompressor,
)
from ..memory.accumulator import MemoryAccumulator
from ..memory.activator import MemoryActivator
from ..memory.consolidator import MemoryConsolidator
from ..memory.decay import MemoryDecay
from ..memory.embedding import EmbeddingProvider, EmbeddingStore
from ..memory.feedback import FeedbackQueue
from ..memory.kernel import MemoryKernel
from ..memory.knowledge_adapter import AstrBotKnowledgeAdapter
from ..memory.maintenance import MemoryMaintenance
from ..memory.unified_recall import UnifiedRecallCoordinator
from ..memory.recall import PlanaRecallEngine
from ..memory.recall_gap import RecallGapTracker
from ..memory.scope import ScopeManager
from ..memory.warehouse_client import MemoryWarehouseClient
from ..memory.warehouse_push import MemoryWarehousePusher
from ..dialogue.remote_task_store import RemoteTaskRunStore
from .models import PlanaState, UserIdentity
from .runtime_memory import PlanaRuntimeMemoryMixin
from ..proactive import ProactiveQueue
from ..prompt import PromptBuilder
from ..relation import ProfileScanner, RelationGraph
from ..resources import ResourceResolver, ResourceStorage
from .runtime_ops import PlanaRuntimeOpsMixin
from .storage import PlanaStorage
from .gallery import PlanaGalleryClient


class PlanaRuntime(
    PlanaRuntimeOpsMixin,
    PlanaRuntimeMemoryMixin,
):
    def __init__(self, data_dir: Path, config, astr_context: Any | None = None):
        self.data_dir = data_dir
        self.config = config
        self.astr_context = astr_context
        self.enabled = bool(config.get("enabled", True))
        configured_mode = str(config.get("mode", "standby"))
        self.configured_mode = PlanaState(mode=configured_mode).normalized().mode
        self.mode = self.configured_mode
        self.inject_prompt = bool(config.get("inject_prompt", True))
        self.record_messages = bool(config.get("record_messages", True))
        self.record_llm_response = bool(config.get("record_llm_response", True))
        self.max_active_memories = int(config.get("max_active_memories", 6))
        self.max_active_semantics = int(config.get("max_active_semantics", 4))
        self.max_active_relations = int(config.get("max_active_relations", 4))
        self.max_prompt_chars = int(config.get("max_prompt_chars", 4000))
        self.memory_inject_max_chars = int(config.get("memory_inject_max_chars", 1800))
        self.memory_inject_cooldown_seconds = int(
            config.get("memory_inject_cooldown_seconds", 60)
        )
        self.memory_inject_min_query_chars = int(
            config.get("memory_inject_min_query_chars", 2)
        )
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
        self.graph_detail_limit = int(config.get("graph_detail_limit", 8))
        self.enable_concept_extraction = bool(
            config.get("enable_concept_extraction", False)
        )
        self.max_concept_keywords = int(config.get("max_concept_keywords", 4))

        # Configurable persona style; if set, replaces the hard-coded identity block.
        self.persona_style: str = str(config.get("persona_style", ""))
        self.enable_structured_memory_extraction = bool(
            config.get("enable_structured_memory_extraction", True)
        )
        self.structured_memory_max_items = int(
            config.get("structured_memory_max_items", 5)
        )
        self.enable_memory_query_planner = bool(
            config.get("enable_memory_query_planner", False)
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
        self.bridge_contract = BridgeContract(bool(config.get("enable_bridge_api", False)))
        self.gallery_client = PlanaGalleryClient(
            config,
            runtime=self,
            allowed_roots=[data_dir.parent / "astrbot_plugin_plana_gallery" / "assets"],
        )
        self.memory_warehouse_client = MemoryWarehouseClient(config, runtime=self)
        self.memory_warehouse_push_messages = bool(config.get("memory_warehouse_push_messages", True))
        self.memory_warehouse_push_llm_responses = bool(config.get("memory_warehouse_push_llm_responses", True))
        self.memory_warehouse_push_maintenance = bool(config.get("memory_warehouse_push_maintenance", True))
        self.memory_warehouse_push_structured_memories = bool(config.get("memory_warehouse_push_structured_memories", True))
        self.memory_warehouse_push_profile_snapshots = bool(config.get("memory_warehouse_push_profile_snapshots", True))
        self.memory_warehouse_pusher = MemoryWarehousePusher(self)
        self.knowledge_adapter = AstrBotKnowledgeAdapter(astr_context, config)
        self.unified_recall = UnifiedRecallCoordinator(self, config)
        self.memory_maintenance_last_run: dict[str, object] = {
            "ran_at": 0,
            "scope_count": 0,
            "warehouse_pushed": 0,
            "failed": 0,
            "last_error": "",
            "scopes": [],
        }
        self.storage = PlanaStorage(data_dir / "plana.sqlite3")
        self.memory_storage = self.storage.memory_storage
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
        self.profile_evidence_storage = ProfileEvidenceStorage(self.storage.db)
        self.profile_scanner = ProfileScanner(self.storage)
        self.profile_scanner.evidence_store = self.profile_evidence_storage
        self.maintenance = MemoryMaintenance(self)
        self.recall_gap_tracker = RecallGapTracker(self.storage.db)
        self.proactive_queue = ProactiveQueue(self.storage.db)
        self.remote_task_runs = RemoteTaskRunStore(self.storage.db)
        self.resource_storage = ResourceStorage(self.storage.db)
        self.resource_resolver = ResourceResolver(self.resource_storage)
        self.feedback_queue = FeedbackQueue(self.storage.db)
        self.scope_manager = ScopeManager(self.storage.db)
        self.embedding_store = EmbeddingStore(self.storage.db)
        self.embedding_provider = EmbeddingProvider(self.embedding_store)
        self.person_info_storage = PersonInfoStorage(self.storage.db)
        self.job_manager = RuntimeJobManager()
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
        self.memory_kernel = MemoryKernel(self)

    def initialize(self) -> None:
        self.storage.initialize()
        self.recall_gap_tracker.initialize()
        self.proactive_queue.initialize()
        self.remote_task_runs.initialize()
        self.resource_storage.initialize()
        self.feedback_queue.initialize()
        self.scope_manager.initialize()
        self.embedding_store.initialize()
        self.person_info_storage.initialize()
        self.profile_evidence_storage.initialize()
        state, changed = self.storage.ensure_state_mode(
            "global",
            self.configured_mode,
            self.configured_mode,
        )
        self.mode = state.mode
        if changed:
            logger.info(
                "Plana configured mode applied to global state: %s",
                self.mode,
            )

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

    def ingest_event(self, event: AstrMessageEvent) -> None:
        if not self.enabled or not self.record_messages:
            return
        identity = self.identity_from_event(event)
        text = event.get_message_str().strip()
        memory_scope = self.resolve_scope(event.unified_msg_origin)
        if self._should_record_message(text):
            try:
                result = self.memory_kernel.ingest_text(
                    memory_scope,
                    identity.global_user_id,
                    f"{identity.nickname}: {text}",
                    kind=MEMORY_KIND_MESSAGE,
                    importance=0.25,
                    source="message_event",
                    actor_id=identity.global_user_id,
                    subject=f"user:{identity.global_user_id}",
                )
                if not result.get("stored"):
                    logger.warning(
                        "Plana message memory not stored: error=%s scope=%s",
                        result.get("error"),
                        memory_scope,
                    )
                elif self.debug_log:
                    logger.debug(
                        "Plana message memory stored: id=%s scope=%s truncated=%s",
                        result.get("memory_id"),
                        memory_scope,
                        result.get("truncated"),
                    )
            except Exception:  # noqa: BLE001
                logger.warning("Plana message memory write failed", exc_info=True)
            self.memory_warehouse_pusher.push_message(event, scope_id=memory_scope, actor_id=identity.global_user_id, actor_name=identity.nickname, content=text)
        if self.enable_relation_graph:
            self.relation_graph.observe_interaction(
                identity,
                text,
                memory_scope,
            )

    def build_prompt_for_event(
        self,
        event: AstrMessageEvent,
        query_override: str | None = None,
        *,
        concept_nodes: list | None = None,
        force_memory: bool = False,
        profile: str = "task",
    ) -> str:
        if not self.enabled or not self.inject_prompt:
            return ""
        state = self.storage.get_state("global", self.mode)
        if state.mode == "silent":
            return ""
        identity = self.identity_from_event(event)
        query = query_override or event.get_message_str().strip()
        memory_scope = self.resolve_scope(event.unified_msg_origin)
        relations = []
        if self.enable_relation_graph:
            relations = self.relation_graph.active_relations(
                identity,
                self.max_active_relations,
                memory_scope,
            )
        context = self.memory_kernel.prompt_context(
            query,
            memory_scope,
            identity,
            relations=relations,
            force=force_memory,
        )
        active_context = context["active_context"]
        # Retrieve concept nodes via spread activation instead of global top-N.
        if concept_nodes is None and self.enable_concept_extraction and query:
            concept_nodes = self._get_relevant_concepts(query)
        # Gather emotion, person_info, and proactive context for prompt.
        emotion_vec = state.emotion if hasattr(state, "emotion") else None
        person_info_data = context.get("person_info")
        proactive_count = self.proactive_queue.pending_count(memory_scope)
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
            profile=profile,
        )
