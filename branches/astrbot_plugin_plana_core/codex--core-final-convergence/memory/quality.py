from __future__ import annotations

from dataclasses import dataclass


SUMMARY_QUALITY_NORMAL = "normal"
SUMMARY_QUALITY_LOW = "low"
SUMMARY_SCHEMA_VERSION = "plana-memory-summary-v1"


@dataclass(frozen=True, slots=True)
class MemorySummaryQuality:
    canonical_summary: str
    persona_summary: str
    summary_quality: str
    summary_schema_version: str = SUMMARY_SCHEMA_VERSION

    @property
    def promotable(self) -> bool:
        return self.summary_quality == SUMMARY_QUALITY_NORMAL


_GENERIC_LOW_QUALITY_TERMS = (
    "某用户",
    "有人",
    "一些事情",
    "普通对话",
    "闲聊",
    "未说明",
    "不明确",
    "someone",
    "some user",
    "something",
    "general chat",
)


def assess_memory_summary_quality(
    *,
    content: str,
    object_value: str = "",
    canonical_summary: str = "",
    persona_summary: str = "",
) -> MemorySummaryQuality:
    """Build LivingMemory-style summary metadata for a structured memory item."""

    canonical = _clean(canonical_summary or object_value or content, 600)
    persona = _clean(persona_summary or content or canonical, 600)
    if not canonical:
        return MemorySummaryQuality("", persona, SUMMARY_QUALITY_LOW)
    lowered = canonical.lower()
    quality = SUMMARY_QUALITY_NORMAL
    if len(canonical) < 6:
        quality = SUMMARY_QUALITY_LOW
    elif any(term in canonical or term in lowered for term in _GENERIC_LOW_QUALITY_TERMS):
        quality = SUMMARY_QUALITY_LOW
    return MemorySummaryQuality(canonical, persona, quality)


def _clean(value: str, limit: int) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    return text[:limit]
