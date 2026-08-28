from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

MEMORY_KIND_MESSAGE: Final = "message"
MEMORY_KIND_LLM_RESPONSE: Final = "llm_response"
MEMORY_KIND_USER_FACT: Final = "user_fact"
MEMORY_KIND_USER_PREFERENCE: Final = "user_preference"
MEMORY_KIND_TASK_FACT: Final = "task_fact"
MEMORY_KIND_TOOL_RESULT: Final = "tool_result"
MEMORY_KIND_RISK_EVENT: Final = "risk_event"
MEMORY_KIND_PROMISE: Final = "promise"
MEMORY_KIND_RELATIONSHIP_NOTE: Final = "relationship_note"
MEMORY_KIND_ARONA_HANDOFF: Final = "arona_handoff"
MEMORY_KIND_PLANA_HANDOFF: Final = "plana_handoff"

LIFE_MEMORY_KINDS: Final[tuple[str, ...]] = (
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_TOOL_RESULT,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
    MEMORY_KIND_ARONA_HANDOFF,
    MEMORY_KIND_PLANA_HANDOFF,
)

ALL_MEMORY_KINDS: Final[tuple[str, ...]] = (
    MEMORY_KIND_MESSAGE,
    MEMORY_KIND_LLM_RESPONSE,
    *LIFE_MEMORY_KINDS,
)


@dataclass(slots=True)
class MemoryRecord:
    id: int
    scope: str
    scope_id: str
    kind: str
    content: str
    importance: float
    source: str
    created_at: int


@dataclass(slots=True)
class SemanticMemory:
    id: int
    scope_id: str
    subject: str
    predicate: str
    object_value: str
    confidence: float
    source: str
    updated_at: int


@dataclass(slots=True)
class ActiveContext:
    memories: list[MemoryRecord] = field(default_factory=list)
    semantics: list[SemanticMemory] = field(default_factory=list)
    relations: list = field(default_factory=list)


@dataclass(slots=True)
class ConsolidationReport:
    scope_id: str
    processed: int = 0
    skipped: int = 0
    semantic_written: int = 0


@dataclass(slots=True)
class DecayReport:
    scope_id: str
    processed: int = 0
    decayed: int = 0
    skipped: int = 0
    archived: int = 0


@dataclass(slots=True)
class ConceptNode:
    id: int
    concept: str
    memory_items: str
    weight: float
    created_at: int
    last_modified: int


@dataclass(slots=True)
class ConceptEdge:
    id: int
    source: str
    target: str
    strength: int
    created_at: int
    last_modified: int
