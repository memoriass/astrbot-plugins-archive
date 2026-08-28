from __future__ import annotations

import math
import re
from time import time

from .models import (
    MEMORY_ATOM_DECAY_EXPONENTIAL,
    MEMORY_ATOM_DECAY_LINEAR,
    MEMORY_ATOM_DECAY_STABLE,
    MEMORY_KIND_BRIDGE_HANDOFF,
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
)


def atom_texts(content: str) -> list[str]:
    clean = " ".join(content.split())
    if not clean:
        return []
    if len(clean) <= 900:
        return [clean]
    segments = []
    buffer = ""
    parts = re.split(r"([.!?;:。！？；：])", clean)
    for index in range(0, len(parts), 2):
        sentence = parts[index].strip()
        if index + 1 < len(parts):
            sentence += parts[index + 1]
        if not sentence:
            continue
        if len(buffer) + len(sentence) > 720 and buffer:
            segments.append(buffer.strip())
            buffer = ""
        buffer = f"{buffer} {sentence}".strip()
        if len(segments) >= 3:
            break
    if buffer:
        segments.append(buffer.strip())
    return [item[:900] for item in segments[:4]] or [clean[:900]]


def infer_atom_type(kind: str) -> str:
    mapping = {
        MEMORY_KIND_MESSAGE: "episodic",
        MEMORY_KIND_LLM_RESPONSE: "episodic",
        MEMORY_KIND_USER_FACT: "factual",
        MEMORY_KIND_USER_PREFERENCE: "preference",
        MEMORY_KIND_TASK_FACT: "task",
        MEMORY_KIND_TOOL_RESULT: "tool",
        MEMORY_KIND_RISK_EVENT: "risk",
        MEMORY_KIND_PROMISE: "promise",
        MEMORY_KIND_RELATIONSHIP_NOTE: "relationship",
        MEMORY_KIND_BRIDGE_HANDOFF: "handoff",
        MEMORY_KIND_PLANA_HANDOFF: "handoff",
    }
    return mapping.get(kind, "unknown")


def default_confidence(kind: str, importance: float) -> float:
    if kind in {MEMORY_KIND_USER_FACT, MEMORY_KIND_USER_PREFERENCE}:
        return 0.78
    if kind in {MEMORY_KIND_RISK_EVENT, MEMORY_KIND_PROMISE}:
        return 0.86
    return round(0.55 + min(max(float(importance), 0.0), 1.0) * 0.25, 4)


def compute_atom_ttl(
    atom_type: str, importance: float, reinforcement_count: int
) -> tuple[float, str]:
    base_and_decay = {
        "episodic": (10.0, MEMORY_ATOM_DECAY_EXPONENTIAL),
        "factual": (180.0, MEMORY_ATOM_DECAY_EXPONENTIAL),
        "preference": (120.0, MEMORY_ATOM_DECAY_STABLE),
        "task": (45.0, MEMORY_ATOM_DECAY_LINEAR),
        "tool": (30.0, MEMORY_ATOM_DECAY_EXPONENTIAL),
        "risk": (365.0, MEMORY_ATOM_DECAY_STABLE),
        "promise": (365.0, MEMORY_ATOM_DECAY_STABLE),
        "relationship": (120.0, MEMORY_ATOM_DECAY_LINEAR),
        "handoff": (90.0, MEMORY_ATOM_DECAY_EXPONENTIAL),
        "unknown": (30.0, MEMORY_ATOM_DECAY_EXPONENTIAL),
    }
    base, decay_type = base_and_decay.get(atom_type, base_and_decay["unknown"])
    importance_factor = 0.5 + min(max(float(importance), 0.0), 1.0)
    reinforce_factor = 1.0 + min(max(reinforcement_count, 0), 5) * 0.12
    ttl_days = max(1.0, round(base * importance_factor * reinforce_factor, 2))
    return ttl_days, decay_type


def compute_decay_score(
    decay_type: str,
    ttl_days: float,
    days_since_access: float,
) -> float:
    effective_ttl = max(1.0, float(ttl_days or 1.0))
    days = max(0.0, float(days_since_access or 0.0))
    if decay_type == MEMORY_ATOM_DECAY_STABLE:
        return 1.0
    if decay_type == MEMORY_ATOM_DECAY_LINEAR:
        return max(0.05, 1.0 - days / effective_ttl)
    half_life = max(0.5, effective_ttl / 2.0)
    return max(0.05, math.exp(-math.log(2) * days / half_life))


def atom_temporal_score(
    last_accessed_at: int,
    ttl_days: float,
    decay_type: str,
    reference_time: int | None = None,
) -> float:
    now = int(reference_time if reference_time is not None else time())
    days = max(0.0, (now - int(last_accessed_at or now)) / 86400.0)
    return round(compute_decay_score(decay_type, ttl_days, days), 4)


def atom_final_score(
    importance: float,
    confidence: float,
    temporal_score: float,
    reinforcement_count: int = 0,
) -> float:
    base = min(max(float(importance), 0.0), 1.0)
    trust = min(max(float(confidence), 0.0), 1.0)
    reinforce = 1.0 + min(max(int(reinforcement_count or 0), 0), 5) * 0.04
    return round(min(1.0, base * trust * temporal_score * reinforce), 4)
