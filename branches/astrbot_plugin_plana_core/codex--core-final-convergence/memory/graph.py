from __future__ import annotations

from collections import deque
from collections.abc import Callable

from .graph_storage import ConceptGraphStorage
from .models import ConceptEdge, ConceptNode
from .tokenizer import SimpleTokenizer

IntegrateCallback = Callable[[str, str], str]

# Similarity threshold for merging related concepts.
_SIMILAR_THRESHOLD = 0.7


class ConceptGraph:
    """In-memory facade over the SQLite-backed concept graph."""

    def __init__(self, storage: ConceptGraphStorage):
        self.storage = storage
        self._tokenizer = SimpleTokenizer(min_length=2)

    def initialize(self) -> None:
        self.storage.initialize()

    def add_concept(
        self,
        concept: str,
        memory: str,
        integrate_callback: IntegrateCallback | None = None,
    ) -> ConceptNode | None:
        normalized = self._normalize_concept(concept)
        content = memory.strip()
        if not normalized or not content:
            return None
        # Check exact match first.
        existing = self.storage.get_node(normalized)
        if existing is not None:
            merged = self._merge_memory(
                existing.memory_items, content, integrate_callback
            )
            return self.storage.save_node(normalized, merged, existing.weight + 1.0)
        # Check for similar existing concepts via cosine similarity.
        similar = self._find_similar_concept(normalized)
        if similar is not None:
            merged = self._merge_memory(
                similar.memory_items, content, integrate_callback
            )
            node = self.storage.save_node(similar.concept, merged, similar.weight + 1.0)
            # Connect the new name to the similar concept for traceability.
            self.connect_concepts(normalized, similar.concept)
            return node
        return self.storage.save_node(normalized, content, 1.0)

    def connect_concepts(self, source: str, target: str) -> ConceptEdge | None:
        left = self._normalize_concept(source)
        right = self._normalize_concept(target)
        if not left or not right or left == right:
            return None
        existing = self.storage.get_edge(left, right)
        strength = 1 if existing is None else existing.strength + 1
        return self.storage.save_edge(left, right, strength)

    def get_neighbors(self, concept: str, depth: int = 1) -> list[ConceptNode]:
        normalized = self._normalize_concept(concept)
        if not normalized or depth <= 0:
            return []
        visited = {normalized}
        queue = deque([(normalized, 0)])
        neighbors: list[ConceptNode] = []
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self.storage.list_edges_for_concept(current):
                other = edge.target if edge.source == current else edge.source
                if other in visited:
                    continue
                visited.add(other)
                node = self.storage.get_node(other)
                if node is not None:
                    neighbors.append(node)
                queue.append((other, current_depth + 1))
        return neighbors

    def get_all_concepts(self) -> list[ConceptNode]:
        return self.storage.load_all_nodes()

    def spread_activation(
        self,
        seeds: list[str],
        max_depth: int = 2,
        top_k: int = 5,
    ) -> list[ConceptNode]:
        """BFS activation spread from seed concepts.

        Each node receives activation proportional to incoming edge strength.
        Returns the top-k activated non-seed nodes sorted by activation desc.
        """
        if not seeds or max_depth <= 0:
            return []
        seed_set: set[str] = set()
        activation: dict[str, float] = {}
        queue: deque[tuple[str, int, float]] = deque()
        for raw in seeds:
            norm = self._normalize_concept(raw)
            if not norm:
                continue
            node = self.storage.get_node(norm)
            if node is None:
                continue
            seed_set.add(norm)
            activation[norm] = node.weight
            queue.append((norm, 0, node.weight))
        while queue:
            current, depth, current_act = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self.storage.list_edges_for_concept(current):
                other = edge.target if edge.source == current else edge.source
                propagated = current_act * (edge.strength / (edge.strength + 1.0))
                old = activation.get(other, 0.0)
                if propagated > old:
                    activation[other] = propagated
                    queue.append((other, depth + 1, propagated))
        # Collect non-seed activated nodes.
        candidates: list[tuple[str, float]] = [
            (concept, act)
            for concept, act in activation.items()
            if concept not in seed_set and act > 0
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        result: list[ConceptNode] = []
        for concept, _act in candidates[:top_k]:
            node = self.storage.get_node(concept)
            if node is not None:
                result.append(node)
        return result

    def forget_concept(self, concept: str) -> bool:
        normalized = self._normalize_concept(concept)
        if not normalized or self.storage.get_node(normalized) is None:
            return False
        self.storage.delete_node(normalized)
        return True

    def summary_text(self) -> str:
        return (
            "Plana concept graph summary:\n"
            f"nodes={self.storage.count_nodes()}\n"
            f"edges={self.storage.count_edges()}"
        )

    def _merge_memory(
        self,
        existing: str,
        new_memory: str,
        integrate_callback: IntegrateCallback | None,
    ) -> str:
        if integrate_callback is not None:
            merged = integrate_callback(existing, new_memory).strip()
            if merged:
                return merged[:4000]
        if new_memory in existing:
            return existing[:4000]
        return f"{existing} | {new_memory}"[:4000]

    def _normalize_concept(self, concept: str) -> str:
        return concept.strip().lower()[:120]

    def _find_similar_concept(self, normalized: str) -> ConceptNode | None:
        """Find an existing concept node similar to *normalized*.

        Scans all nodes and returns the best match above the similarity
        threshold.  For performance, limits the scan to the top-200 nodes
        by weight.
        """
        all_nodes = self.storage.load_all_nodes()
        if not all_nodes:
            return None
        best_node: ConceptNode | None = None
        best_sim = 0.0
        for node in all_nodes[:200]:
            sim = self._tokenizer.cosine_similarity(normalized, node.concept)
            if sim >= _SIMILAR_THRESHOLD and sim > best_sim:
                best_sim = sim
                best_node = node
        return best_node
