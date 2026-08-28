from __future__ import annotations

from typing import TYPE_CHECKING

from ..plugin.storage import PlanaStorage
from .graph import ConceptGraph
from .models import ActiveContext
from .tokenizer import SimpleTokenizer

if TYPE_CHECKING:
    from ..identity.models import UserIdentity
    from ..plugin.models import RelationEdge


class MemoryActivator:
    def __init__(
        self,
        storage: PlanaStorage,
        max_memories: int,
        max_semantics: int,
        max_relations: int,
        concept_graph: ConceptGraph | None = None,
    ):
        self.storage = storage
        self.max_memories = max(1, max_memories)
        self.max_semantics = max(0, max_semantics)
        self.max_relations = max(0, max_relations)
        self.concept_graph = concept_graph
        self.tokenizer = SimpleTokenizer(min_length=2)

    def activate(
        self,
        query: str,
        scope_id: str,
        identity: UserIdentity,
        relations: list[RelationEdge] | None = None,
    ) -> ActiveContext:
        active_relations = (
            relations
            if relations is not None
            else self.storage.related_edges(
                identity.global_user_id,
                self.max_relations,
                scope_id,
            )
        )
        # Expand query with concept graph spread activation.
        expanded_query = self._expand_query(query)
        return ActiveContext(
            memories=self.storage.search_memories(
                scope_id, expanded_query, self.max_memories
            ),
            semantics=self.storage.search_semantics(
                scope_id, expanded_query, self.max_semantics
            ),
            relations=active_relations[: self.max_relations],
        )

    def _expand_query(self, query: str) -> str:
        """Expand query using concept graph spread activation."""
        if not query.strip() or self.concept_graph is None:
            return query
        terms = self.tokenizer.search_terms(query)
        if not terms:
            return query
        activated = self.concept_graph.spread_activation(
            seeds=terms[:4], max_depth=2, top_k=3
        )
        if not activated:
            return query
        extra = " ".join(node.concept for node in activated)
        return f"{query} {extra}"
