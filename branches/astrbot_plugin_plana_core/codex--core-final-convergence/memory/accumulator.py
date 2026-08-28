from __future__ import annotations

from astrbot.api.provider import Provider

from ..plugin.storage import PlanaStorage
from .compressor import MemoryCompressor


class MemoryAccumulator:
    """Periodically compress recent memories into concept graph entries.

    Designed to be called from an async task or explicit command.
    Picks unlinked recent memories and feeds them to MemoryCompressor.
    """

    def __init__(
        self,
        storage: PlanaStorage,
        compressor: MemoryCompressor,
        batch_size: int = 8,
    ):
        self.storage = storage
        self.compressor = compressor
        self.batch_size = max(1, min(batch_size, 32))

    async def accumulate(
        self,
        scope_id: str,
        provider: Provider | None,
    ) -> dict[str, int]:
        """Compress unprocessed memories for a scope.

        Returns a dict with processed / written / skipped counts.
        """
        if provider is None:
            return {"processed": 0, "written": 0, "skipped": 0}
        candidates = self.storage.recent_memories(scope_id, self.batch_size * 2)
        # Filter out already-linked memories (consolidation tag).
        batch = []
        skipped = 0
        for mem in candidates:
            if len(batch) >= self.batch_size:
                break
            if self.storage.memory_has_link(mem.id, "concept_compress"):
                skipped += 1
                continue
            batch.append(mem)
        if not batch:
            return {"processed": 0, "written": 0, "skipped": skipped}
        written = await self.compressor.compress(batch, provider)
        # Mark processed memories.
        for mem in batch:
            self.storage.link_memory(
                mem.id, "concept_compress", f"scope:{scope_id}", 0.50
            )
        return {
            "processed": len(batch),
            "written": written,
            "skipped": skipped,
        }
