from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from .models import (
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_TOOL_RESULT,
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_DEFAULT_TARGET_KINDS = (
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
    MEMORY_KIND_TASK_FACT,
    MEMORY_KIND_TOOL_RESULT,
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
)
_RECALL_HINTS = (
    "之前",
    "以前",
    "曾经",
    "上次",
    "刚才",
    "还记得",
    "记得",
    "记忆",
    "回忆",
    "继续",
    "那个",
    "那次",
    "我们说过",
    "我说过",
    "偏好",
    "喜欢",
    "讨厌",
    "习惯",
    "约定",
    "答应",
    "承诺",
    "计划",
    "任务",
    "我是谁",
    "是谁",
    "叫什么",
    "我绑定的",
    "我们绑定的",
    "我负责的",
    "我们负责的",
    "我的实例",
    "我的服务器",
    "我的订阅",
    "那个实例",
    "那个机器人",
    "那个下载器",
    "发给他",
    "私发给他",
    "the one we discussed",
    "what did we decide",
    "what did we agree",
    "we agreed",
    "previously",
    "last time",
    "my instance",
    "my server",
    "my subscriptions",
)
_DEFAULT_TIMEOUT_SECONDS = 1.2


@dataclass(slots=True)
class MemoryQueryPlan:
    should_retrieve: bool
    query: str
    target_kinds: tuple[str, ...] = ()
    reason: str = ""


class LLMMemoryQueryPlanner:
    """Plan a memory retrieval query before building Plana prompt."""

    async def plan(self, user_text: str, provider) -> MemoryQueryPlan:
        text = user_text.strip()
        if not text:
            return MemoryQueryPlan(False, "", (), "empty")
        fallback = self._fallback(text)
        if provider is None or not fallback.should_retrieve:
            return fallback
        try:
            response = await asyncio.wait_for(
                provider.text_chat(
                    prompt=self._prompt(text),
                    system_prompt=(
                        "You decide whether Plana Core should retrieve memory. "
                        "Return strict JSON only."
                    ),
                ),
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return fallback
        return self._parse(str(getattr(response, "completion_text", "") or ""), text)

    def _prompt(self, user_text: str) -> str:
        kinds = ", ".join(_DEFAULT_TARGET_KINDS)
        return (
            "Given the user message, decide if long-term memory retrieval is useful.\n"
            'Return JSON: {"should_retrieve":true,"query":"...",'
            '"target_kinds":["user_fact"],"reason":"..."}.\n'
            f"Allowed target_kinds: {kinds}.\n"
            "Rules:\n"
            "1. query should be one precise memory search question.\n"
            "2. Use should_retrieve=false for pure greetings or unrelated one-off text.\n"
            "3. Do not include explanations outside JSON.\n\n"
            f"User message:\n{user_text[:800]}"
        )

    def _fallback(self, text: str) -> MemoryQueryPlan:
        should = any(hint in text for hint in _RECALL_HINTS)
        return MemoryQueryPlan(should, text[:300] if should else "", (), "rule_hint")

    def _parse(self, raw: str, fallback_query: str) -> MemoryQueryPlan:
        data = self._load_json(raw)
        if not data:
            return self._fallback(fallback_query)
        should = bool(data.get("should_retrieve", False))
        query = " ".join(str(data.get("query", "") or "").split())[:300]
        reason = " ".join(str(data.get("reason", "") or "").split())[:120]
        kinds = data.get("target_kinds", [])
        target_kinds = self._clean_kinds(kinds)
        if should and not query:
            query = fallback_query[:300]
        return MemoryQueryPlan(should, query, target_kinds, reason)

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

    def _clean_kinds(self, values: Any) -> tuple[str, ...]:
        if not isinstance(values, list):
            return ()
        allowed = set(_DEFAULT_TARGET_KINDS)
        cleaned = []
        for value in values:
            kind = str(value or "").strip()
            if kind in allowed and kind not in cleaned:
                cleaned.append(kind)
        return tuple(cleaned[:6])
