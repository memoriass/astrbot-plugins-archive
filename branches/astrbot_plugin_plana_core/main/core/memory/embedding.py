"""Embedding-based semantic retrieval for Plana Core.

Provides optional vector embedding support:
- Stores embeddings in SQLite as JSON arrays (lightweight, no external deps)
- Computes cosine similarity in Python for re-ranking
- Integrates with AstrBot's LLM provider for embedding generation
- Falls back gracefully when no embedding provider is available
"""

from __future__ import annotations

import json
import math
from time import time
from typing import Any

from ..db import Database


class EmbeddingStore:
    """SQLite-backed embedding storage with cosine similarity search."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id INTEGER PRIMARY KEY,
                    scope_id TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_embeddings_scope
                    ON memory_embeddings(scope_id);
                """
            )

    def store(
        self,
        memory_id: int,
        scope_id: str,
        embedding: list[float],
        model: str = "",
    ) -> None:
        """Store an embedding vector for a memory."""
        now = int(time())
        vec_json = json.dumps(embedding)
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO memory_embeddings
                   (memory_id, scope_id, embedding, dim, model, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (memory_id, scope_id, vec_json, len(embedding), model, now),
            )

    def get(self, memory_id: int) -> list[float] | None:
        """Retrieve embedding for a memory."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM memory_embeddings WHERE memory_id=?",
                (memory_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def search_similar(
        self,
        scope_id: str,
        query_embedding: list[float],
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Find memories with most similar embeddings via cosine similarity.

        Scans all embeddings in scope (suitable for <10k memories per scope).
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT memory_id, embedding FROM memory_embeddings WHERE scope_id=?",
                (scope_id,),
            ).fetchall()

        if not rows:
            return []

        results: list[tuple[int, float]] = []
        for row in rows:
            mem_id = row[0]
            stored_vec = json.loads(row[1])
            sim = _cosine_similarity(query_embedding, stored_vec)
            if sim >= min_similarity:
                results.append((mem_id, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return [
            {"memory_id": mem_id, "similarity": round(sim, 6)}
            for mem_id, sim in results[:limit]
        ]

    def count(self, scope_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM memory_embeddings WHERE scope_id=?",
                (scope_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def has_embedding(self, memory_id: int) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM memory_embeddings WHERE memory_id=? LIMIT 1",
                (memory_id,),
            ).fetchone()
        return row is not None

    def delete(self, memory_id: int) -> bool:
        with self.db.connect() as conn:
            affected = conn.execute(
                "DELETE FROM memory_embeddings WHERE memory_id=?", (memory_id,)
            ).rowcount
        return affected > 0

    def cleanup_orphans(self) -> int:
        """Remove embeddings for memories that no longer exist."""
        with self.db.connect() as conn:
            affected = conn.execute(
                """DELETE FROM memory_embeddings
                   WHERE memory_id NOT IN (SELECT id FROM episodic_memories)"""
            ).rowcount
        return affected


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec_a) != len(vec_b) or not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingProvider:
    """Wraps an AstrBot LLM provider to generate text embeddings.

    If the provider does not support embeddings, falls back to None.
    """

    def __init__(self, store: EmbeddingStore):
        self.store = store
        self._provider: Any = None
        self._model: str = ""

    def set_provider(self, provider: Any, model: str = "") -> None:
        """Set the LLM provider to use for embedding generation."""
        self._provider = provider
        self._model = model

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def embed_text(self, text: str) -> list[float] | None:
        """Generate embedding for a text string."""
        if not self._provider:
            return None
        try:
            # Try AstrBot's provider embedding API
            if hasattr(self._provider, "get_embeddings"):
                result = await self._provider.get_embeddings([text])
                if result and len(result) > 0:
                    return result[0]
            if hasattr(self._provider, "embed"):
                result = await self._provider.embed(text)
                if result:
                    return result
        except Exception:
            pass
        return None

    async def embed_and_store(self, memory_id: int, scope_id: str, text: str) -> bool:
        """Generate and store embedding for a memory."""
        vec = await self.embed_text(text)
        if vec is None:
            return False
        self.store.store(memory_id, scope_id, vec, model=self._model)
        return True

    async def semantic_search(
        self,
        scope_id: str,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Search memories by semantic similarity to query."""
        query_vec = await self.embed_text(query)
        if query_vec is None:
            return []
        return self.store.search_similar(
            scope_id, query_vec, limit=limit, min_similarity=min_similarity
        )
