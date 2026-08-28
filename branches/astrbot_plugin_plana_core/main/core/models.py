from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Re-export from subpackages for backwards compatibility
from .identity import SessionStream, UserIdentity  # noqa: F401
from .memory.models import (  # noqa: F401
    ALL_MEMORY_KINDS,
    LIFE_MEMORY_KINDS,
    MEMORY_KIND_ARONA_HANDOFF,
    MEMORY_KIND_LLM_RESPONSE,
    MEMORY_KIND_MESSAGE,
    MEMORY_KIND_PLANA_HANDOFF,
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_TOOL_RESULT,
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
    ActiveContext,
    ConsolidationReport,
    DecayReport,
    MemoryRecord,
    SemanticMemory,
)
from .persona import PlanaState  # noqa: F401


@dataclass(slots=True)
class RelationEdge:
    id: int
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    confidence: float
    evidence: str
    updated_at: int


@dataclass(slots=True)
class TaskRecord:
    id: int
    scope_id: str
    owner_id: str
    objective: str
    status: str
    risk_level: str
    created_at: int
    updated_at: int


@dataclass(slots=True)
class PlannerStep:
    id: int
    task_id: int
    step_index: int
    instruction: str
    status: str
    created_at: int
    updated_at: int


@dataclass(slots=True)
class AronaTaskRequest:
    task_id: str
    objective: str
    source: str = "arona"
    user_context: dict[str, Any] | None = None
    memory_context: list[str] | None = None
    constraints: list[str] | None = None
