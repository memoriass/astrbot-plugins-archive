from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import time

@dataclass(frozen=True, slots=True)
class ExecutionContext:
    context_id: str
    scope_id: str
    actor_id: str
    original_task: str
    service_ref: str
    capability: str
    credential_ref: str = ""
    lane: str = "interactive"
    read_only: bool = True
    reason: str = ""
    arguments: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    created_at: float = field(default_factory=time)

    def execution_refs(self) -> dict[str, str]:
        return {"service_ref": self.service_ref, "capability": self.capability, "credential_ref": self.credential_ref}

class ExecutionContextRegistry:
    """Stores bounded pending handoffs; contexts are consumed after confirmation."""

    def __init__(self, *, max_entries: int = 256, ttl_seconds: int = 1800) -> None:
        self.max_entries = max(8, int(max_entries))
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._contexts: dict[str, ExecutionContext] = {}

    def create(
        self,
        *,
        scope_id: str,
        actor_id: str,
        original_task: str,
        service_ref: str,
        capability: str,
        lane: str,
        read_only: bool,
        reason: str,
        credential_ref: str = "",
        arguments: dict[str, str | int | float | bool | None] | None = None,
    ) -> ExecutionContext:
        self.cleanup()
        if len(self._contexts) >= self.max_entries:
            oldest = min(self._contexts.values(), key=lambda item: item.created_at)
            self._contexts.pop(oldest.context_id, None)
        context = ExecutionContext(
            context_id=f"exec-{uuid.uuid4()}", scope_id=str(scope_id or "global")[:200], actor_id=str(actor_id or "user")[:200],
            original_task=" ".join(str(original_task or "").split())[:1200], service_ref=str(service_ref or "codex.runner")[:120],
            capability=str(capability or "codex.interactive")[:120], credential_ref=str(credential_ref or "")[:120],
            lane=lane if lane in {"interactive", "long"} else "interactive", read_only=bool(read_only),
            reason=" ".join(str(reason or "").split())[:200],
            arguments=dict(arguments or {}),
        )
        self._contexts[context.context_id] = context
        return context

    def consume(self, context_id: str, *, scope_id: str, actor_id: str) -> ExecutionContext | None:
        self.cleanup()
        context = self._contexts.get(str(context_id or ""))
        if context is None or context.scope_id != scope_id or context.actor_id != actor_id:
            return None
        return self._contexts.pop(context.context_id)

    def discard(self, context_id: str) -> None:
        self._contexts.pop(str(context_id or ""), None)

    def cleanup(self) -> int:
        cutoff = time() - self.ttl_seconds
        expired = [key for key, value in self._contexts.items() if value.created_at < cutoff]
        for key in expired:
            self._contexts.pop(key, None)
        return len(expired)
