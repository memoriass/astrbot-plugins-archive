"""Lightweight active recall and RRF fusion for Plana Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .embedding import EmbeddingProvider


@dataclass(slots=True)
class RecallCandidate:
    key: str
    route: str
    title: str
    content: str
    source: str
    kind: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class PlanaRecallEngine:
    """Fuse episodic memory, semantic profile and concept routes.

    The scoring follows Reciprocal Rank Fusion:
    score(d) = sum(weight(route) / (rrf_k + rank_i(d))).
    """

    def __init__(
        self,
        runtime: Any,
        rrf_k: int = 60,
        include_semantic: bool = True,
        include_concept: bool = True,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.runtime = runtime
        self.rrf_k = max(1, int(rrf_k))
        self.include_semantic = include_semantic
        self.include_concept = include_concept
        self.embedding_provider = embedding_provider
        self.route_weights = {
            "memory": 0.55,
            "semantic": 0.30,
            "concept": 0.30,
            "embedding": 0.50,
        }
        self.cross_route_bonus = 0.08

    def recall(
        self,
        scope: str = "global",
        query: str = "",
        kind: str = "",
        k: int = 5,
    ) -> dict[str, object]:
        safe_k = max(1, min(int(k or 5), 50))
        clean_query = (query or "").strip()
        clean_kind = (kind or "").strip()
        route_limit = max(safe_k * 2, safe_k)
        routes = self._routes(scope, clean_query, clean_kind, route_limit)
        fused = self._fuse(routes, safe_k)
        return {
            "scope": scope,
            "query": clean_query,
            "kind": clean_kind,
            "count": len(fused),
            "routes": {name: len(items) for name, items in routes.items()},
            "results": fused,
            "explain": {
                "fusion": "reciprocal_rank_fusion",
                "rrf_k": self.rrf_k,
                "document_route_weight": self.route_weights["memory"],
                "graph_route_weight": self.route_weights["semantic"],
                "concept_route_weight": self.route_weights["concept"],
                "cross_route_bonus": self.cross_route_bonus,
            },
        }

    def _routes(
        self, scope: str, query: str, kind: str, limit: int
    ) -> dict[str, list[RecallCandidate]]:
        routes: dict[str, list[RecallCandidate]] = {
            "memory": self._memory_candidates(scope, query, kind, limit)
        }
        if self.include_semantic:
            routes["semantic"] = self._semantic_candidates(scope, query, limit)
        if self.include_concept:
            routes["concept"] = self._concept_candidates(query, limit)
        if self.embedding_provider and self.embedding_provider.available and query:
            emb_results = self._embedding_candidates(scope, query, limit)
            if emb_results:
                routes["embedding"] = emb_results
        return routes

    def _memory_candidates(
        self, scope: str, query: str, kind: str, limit: int
    ) -> list[RecallCandidate]:
        storage = self.runtime.storage
        if kind and query:
            items = storage.search_memories_by_kind(scope, query, kind, limit)
        elif kind:
            items = storage.recent_memories_by_kind(scope, kind, limit)
        elif query:
            items = storage.search_memories(scope, query, limit)
        else:
            items = storage.recent_memories(scope, limit)
        return [
            RecallCandidate(
                key=f"memory:{item.id}",
                route="memory",
                title=f"memory#{item.id}",
                content=item.content,
                kind=item.kind,
                source=item.source,
                metadata={
                    "id": item.id,
                    "importance": round(float(item.importance), 4),
                    "created_at": item.created_at,
                },
            )
            for item in items
        ]

    def _semantic_candidates(
        self, scope: str, query: str, limit: int
    ) -> list[RecallCandidate]:
        if not hasattr(self.runtime.storage, "search_semantics"):
            return []
        items = self.runtime.storage.search_semantics(scope, query, limit)
        return [
            RecallCandidate(
                key=f"semantic:{item.id}",
                route="semantic",
                title=f"{item.subject}.{item.predicate}",
                content=f"{item.subject} {item.predicate} {item.object_value}",
                source=item.source,
                metadata={
                    "id": item.id,
                    "confidence": round(float(item.confidence), 4),
                    "updated_at": item.updated_at,
                },
            )
            for item in items
        ]

    def _concept_candidates(self, query: str, limit: int) -> list[RecallCandidate]:
        if query and hasattr(self.runtime, "_get_relevant_concepts"):
            items = self.runtime._get_relevant_concepts(query) or []  # noqa: SLF001
            items = items[:limit]
        else:
            items = self.runtime.concept_graph.storage.load_all_nodes()[:limit]
        return [
            RecallCandidate(
                key=f"concept:{item.id}",
                route="concept",
                title=item.concept,
                content=item.memory_items or item.concept,
                source="concept_graph",
                metadata={
                    "id": item.id,
                    "weight": round(float(item.weight), 4),
                    "last_modified": item.last_modified,
                },
            )
            for item in items
        ]

    def _embedding_candidates(
        self, scope: str, query: str, limit: int
    ) -> list[RecallCandidate]:
        """Use embedding store for semantic similarity search.

        Requires runtime._last_query_embedding to be set (by async pre-compute).
        """
        if not self.embedding_provider:
            return []
        store = self.embedding_provider.store
        cached_vec = getattr(self.runtime, "_last_query_embedding", None)
        if cached_vec is None:
            return []
        results = store.search_similar(scope, cached_vec, limit=limit)
        if not results:
            return []
        storage = self.runtime.storage
        candidates = []
        for hit in results:
            mem_id = hit["memory_id"]
            with storage.db.connect() as conn:
                row = conn.execute(
                    "SELECT id, kind, content, importance, source, created_at"
                    " FROM episodic_memories WHERE id=?",
                    (mem_id,),
                ).fetchone()
            if not row:
                continue
            candidates.append(
                RecallCandidate(
                    key=f"memory:{row[0]}",
                    route="embedding",
                    title=f"memory#{row[0]}",
                    content=row[2],
                    kind=row[1],
                    source=row[4],
                    metadata={
                        "id": row[0],
                        "importance": round(float(row[3]), 4),
                        "created_at": row[5],
                        "similarity": hit["similarity"],
                    },
                )
            )
        return candidates

    def _fuse(
        self, routes: dict[str, list[RecallCandidate]], top_k: int
    ) -> list[dict[str, object]]:
        candidates: dict[str, RecallCandidate] = {}
        scores: dict[str, float] = {}
        breakdown: dict[str, dict[str, float]] = {}
        route_hits: dict[str, set[str]] = {}
        for route, items in routes.items():
            route_hits[route] = set()
            weight = self.route_weights.get(route, 0.25)
            for rank, item in enumerate(items, start=1):
                candidates.setdefault(item.key, item)
                route_hits[route].add(item.key)
                signal = weight / (self.rrf_k + rank)
                scores[item.key] = scores.get(item.key, 0.0) + signal
                breakdown.setdefault(item.key, {})[f"{route}_rrf"] = round(signal, 6)
        for key in candidates:
            hit_count = sum(1 for hits in route_hits.values() if key in hits)
            if hit_count > 1:
                scores[key] += self.cross_route_bonus
                breakdown.setdefault(key, {})["cross_route_bonus"] = (
                    self.cross_route_bonus
                )
        ordered = sorted(candidates, key=lambda key: scores.get(key, 0.0), reverse=True)
        return [
            self._serialize(candidates[key], scores[key], breakdown[key])
            for key in ordered[:top_k]
        ]

    @staticmethod
    def _serialize(
        item: RecallCandidate, score: float, score_breakdown: dict[str, float]
    ) -> dict[str, object]:
        return {
            "id": item.key,
            "route": item.route,
            "title": item.title,
            "kind": item.kind,
            "content": item.content,
            "source": item.source,
            "score": round(score, 6),
            "score_breakdown": score_breakdown,
            "metadata": item.metadata,
        }
