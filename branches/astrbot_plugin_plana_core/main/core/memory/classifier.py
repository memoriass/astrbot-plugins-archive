from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .models import (
    LIFE_MEMORY_KINDS,
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_ALLOWED_KINDS = set(LIFE_MEMORY_KINDS)
_DEFAULT_KINDS = (
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
)


@dataclass(slots=True)
class StructuredMemoryItem:
    kind: str
    content: str
    subject: str = ""
    predicate: str = ""
    object_value: str = ""
    confidence: float = 0.6
    importance: float = 0.5


class LLMStructuredMemoryExtractor:
    """Extract durable life-memory facts from one user/assistant exchange."""

    def __init__(self, max_items: int = 5):
        self.max_items = max(1, min(max_items, 10))

    async def extract(
        self,
        *,
        user_id: str,
        nickname: str,
        user_text: str,
        response_text: str,
        provider,
    ) -> list[StructuredMemoryItem]:
        if provider is None or not (user_text.strip() or response_text.strip()):
            return []
        try:
            response = await provider.text_chat(
                prompt=self._prompt(user_id, nickname, user_text, response_text),
                system_prompt=(
                    "You extract durable memory facts for Plana Core. "
                    "Return strict JSON only. Do not include commentary."
                ),
            )
        except Exception:  # noqa: BLE001
            return []
        raw = str(getattr(response, "completion_text", "") or "")
        return self._parse_items(raw)

    def _prompt(
        self, user_id: str, nickname: str, user_text: str, response_text: str
    ) -> str:
        kinds = ", ".join(_DEFAULT_KINDS)
        return (
            "Extract only stable, useful long-term memories from this exchange.\n"
            "Ignore small talk, transient wording, and private credentials.\n"
            f"Allowed kind values: {kinds}.\n"
            "Return JSON with this schema exactly:\n"
            '{"items":[{"kind":"user_fact","content":"...",'
            '"subject":"user:<id>","predicate":"short_key",'
            '"object_value":"...","confidence":0.0,"importance":0.0}]}\n'
            "Rules:\n"
            "1. subject should be user:<id>, plana:core, task, or relation:<id>.\n"
            "2. predicate must be short snake_case when semantic fields are useful.\n"
            "3. content must be one concise sentence that can be stored directly.\n"
            "4. Use risk_event for risky operations or security constraints.\n"
            "5. Use promise for commitments, reminders, or future obligations.\n"
            "6. Return at most "
            f"{self.max_items} items. Return [] if nothing durable exists.\n\n"
            f"User id: {user_id}\nNickname: {nickname}\n"
            f"User message:\n{user_text[:1200]}\n\n"
            f"Plana response:\n{response_text[:1200]}"
        )

    def _parse_items(self, raw: str) -> list[StructuredMemoryItem]:
        data = self._load_json(raw)
        raw_items = data.get("items", []) if isinstance(data, dict) else []
        items: list[StructuredMemoryItem] = []
        for value in raw_items:
            if not isinstance(value, dict):
                continue
            item = self._coerce_item(value)
            if item is None:
                continue
            items.append(item)
            if len(items) >= self.max_items:
                break
        return items

    def _load_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        match = _JSON_BLOCK_RE.search(text)
        if match:
            text = match.group(1)
        elif "{" in text and "}" in text:
            text = text[text.find("{") : text.rfind("}") + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _coerce_item(self, value: dict[str, Any]) -> StructuredMemoryItem | None:
        content = self._clean(value.get("content", ""), 500)
        if not content:
            return None
        kind = self._clean(value.get("kind", ""), 40)
        if kind not in _ALLOWED_KINDS:
            kind = MEMORY_KIND_USER_FACT
        return StructuredMemoryItem(
            kind=kind,
            content=content,
            subject=self._clean(value.get("subject", ""), 160),
            predicate=self._clean(value.get("predicate", ""), 80),
            object_value=self._clean(value.get("object_value", ""), 600),
            confidence=self._clamp(value.get("confidence", 0.6)),
            importance=self._clamp(value.get("importance", 0.5)),
        )

    def _clean(self, value: Any, limit: int) -> str:
        text = " ".join(str(value or "").replace("\n", " ").split())
        return text[:limit]

    def _clamp(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.5
        return min(max(number, 0.0), 1.0)
