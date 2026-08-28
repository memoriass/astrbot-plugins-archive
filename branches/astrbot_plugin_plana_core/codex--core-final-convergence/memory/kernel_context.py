from __future__ import annotations

import copy
import time
from types import SimpleNamespace
from typing import Any


class MemoryKernelContextMixin:
    def _prompt_payload(
        self,
        scope: str,
        identity: Any,
        active_context: Any,
        skipped_reason: str,
    ) -> dict[str, Any]:
        profile = self.get_person_profile(
            scope,
            str(getattr(identity, "global_user_id", "") or ""),
            self._runtime_int("max_active_semantics", 4),
        )
        active_context = self._merge_profile_semantics(active_context, profile)
        return {
            "scope": scope,
            "active_context": active_context,
            "person_info": profile.get("person"),
            "person_summary": profile.get("person_summary", ""),
            "skipped_reason": skipped_reason,
            "limits": {
                "max_chars": self._prompt_max_chars(),
                "cooldown_seconds": self._prompt_cooldown_seconds(),
            },
        }

    def _merge_profile_semantics(
        self,
        active_context: Any,
        profile: dict[str, Any],
    ) -> Any:
        max_semantics = self._runtime_int("max_active_semantics", 4)
        if max_semantics <= 0:
            return active_context
        profile_semantics = list(profile.get("semantics") or [])
        current_semantics = list(getattr(active_context, "semantics", []))
        if not profile_semantics:
            return active_context
        memories = list(getattr(active_context, "memories", []))
        remaining = self._prompt_max_chars() - sum(
            len(str(getattr(item, "content", ""))) for item in memories
        )
        if remaining <= 0:
            return active_context
        merged = []
        seen: set[tuple[str, str, str]] = set()
        for item in profile_semantics + current_semantics:
            key = (
                str(getattr(item, "subject", "")),
                str(getattr(item, "predicate", "")),
                str(getattr(item, "object_value", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            cloned = copy.copy(item)
            text = str(getattr(cloned, "object_value", ""))
            clipped = self._clip_text(text, min(280, remaining))
            if not clipped:
                continue
            cloned.object_value = clipped
            merged.append(cloned)
            remaining -= len(clipped)
            if len(merged) >= max_semantics:
                break
        return SimpleNamespace(
            memories=memories,
            semantics=merged,
            relations=list(getattr(active_context, "relations", [])),
        )

    def _concepts(self, query: str, limit: int) -> list[Any]:
        if query and hasattr(self.runtime, "_get_relevant_concepts"):
            active = self.runtime._get_relevant_concepts(query)  # noqa: SLF001
            if active:
                return active[:limit]
        return self.runtime.concept_graph.storage.load_all_nodes()[:limit]

    def _bounded_active_context(self, active_context: Any) -> Any:
        budget = self._prompt_max_chars()
        memories = []
        semantics = []
        used = 0
        for item in list(getattr(active_context, "memories", [])):
            if _is_volatile_operational_memory(item):
                continue
            remaining = budget - used
            if remaining <= 0:
                break
            cloned = copy.copy(item)
            text = str(getattr(cloned, "content", ""))
            clipped = self._clip_text(text, min(360, remaining))
            if not clipped:
                break
            cloned.content = clipped
            memories.append(cloned)
            used += len(clipped)
            if used >= budget:
                break
        remaining = max(0, budget - used)
        for item in list(getattr(active_context, "semantics", [])):
            if remaining <= 0:
                break
            cloned = copy.copy(item)
            text = str(getattr(cloned, "object_value", ""))
            clipped = self._clip_text(text, min(280, remaining))
            if not clipped:
                break
            cloned.object_value = clipped
            semantics.append(cloned)
            remaining -= len(clipped)
            if remaining <= 0:
                break
        return SimpleNamespace(
            memories=memories,
            semantics=semantics,
            relations=list(getattr(active_context, "relations", []))[
                : self._runtime_int("max_active_relations", 4)
            ],
        )
    def _scope(self, scope_id: str) -> str:
        raw = str(scope_id or "global")
        if hasattr(self.runtime, "resolve_scope"):
            return self.runtime.resolve_scope(raw)
        return raw

    def _cooldown_skip_reason(
        self,
        scope: str,
        identity: Any,
        query: str,
        force: bool,
    ) -> str:
        if force:
            return ""
        if len(query) < self._runtime_int("memory_inject_min_query_chars", 2):
            return "query_too_short"
        cooldown = self._prompt_cooldown_seconds()
        if cooldown <= 0:
            return ""
        user_id = str(getattr(identity, "global_user_id", "") or "")
        key = f"{scope}|{user_id}"
        now = int(time.time())
        last = self._last_prompt_context.get(key)
        if not last:
            return ""
        last_at, last_query = last
        if now - last_at >= cooldown:
            return ""
        if self._query_terms(query) == self._query_terms(last_query):
            return "cooldown_same_query"
        return ""

    def _mark_prompt_context(self, scope: str, identity: Any, query: str) -> None:
        user_id = str(getattr(identity, "global_user_id", "") or "")
        self._last_prompt_context[f"{scope}|{user_id}"] = (int(time.time()), query)

    def _empty_context(self, relations: list[Any] | None = None) -> Any:
        return SimpleNamespace(memories=[], semantics=[], relations=relations or [])

    def _runtime_int(self, name: str, default: int) -> int:
        sentinel = object()
        raw = getattr(self.runtime, name, sentinel)
        if raw is sentinel:
            config = getattr(self.runtime, "config", {}) or {}
            getter = getattr(config, "get", None)
            raw = getter(name, default) if getter is not None else default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(0, value)

    def _prompt_max_chars(self) -> int:
        prompt_budget = max(1, self._runtime_int("max_prompt_chars", 4000))
        default = min(1800, prompt_budget)
        return self._bounded_int(
            self._runtime_int("memory_inject_max_chars", default),
            default,
            minimum=min(300, prompt_budget),
            maximum=prompt_budget,
        )

    def _prompt_cooldown_seconds(self) -> int:
        value = self._runtime_int("memory_inject_cooldown_seconds", 60)
        return self._bounded_int(value, 60, minimum=0, maximum=3600)

    def _query_terms(self, query: str) -> tuple[str, ...]:
        return tuple(sorted({item.lower() for item in query.split() if len(item) >= 2}))

    def _clip_text(self, text: str, limit: int) -> str:
        clean = " ".join(str(text or "").split())
        if limit <= 0:
            return ""
        if limit <= 3:
            return clean[:limit]
        return clean if len(clean) <= limit else clean[: max(0, limit - 3)].rstrip() + "..."

    def _memory_content(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        if limit <= 80:
            return text[:limit]
        marker = f" ...[truncated {len(text) - limit} chars]... "
        head = max(20, (limit - len(marker)) // 2)
        tail = max(20, limit - len(marker) - head)
        return f"{text[:head].rstrip()}{marker}{text[-tail:].lstrip()}"[:limit]

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        try:
            parsed = int(value if value is not None else default)
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, max(1, maximum)))

    @staticmethod
    def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(parsed, maximum))

    @staticmethod
    def _clamp(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = 0.0
        return max(0.0, min(parsed, 1.0))


def _is_volatile_operational_memory(item: Any) -> bool:
    if str(getattr(item, "kind", "") or "") != "llm_response":
        return False
    text = str(getattr(item, "content", "") or "").casefold()
    subjects = (
        "插件",
        "模块",
        "工具",
        "权限",
        "网络",
        "plugin",
        "module",
        "tool",
        "permission",
        "network",
        "mikan",
        "ani-rss",
    )
    states = (
        "未加载",
        "尚未加载",
        "不可用",
        "权限受限",
        "无法直接",
        "发生了 60 秒超时",
        "没有返回任何结果",
        "unavailable",
        "not loaded",
        "permission denied",
        "timed out",
    )
    return any(subject in text for subject in subjects) and any(
        state in text for state in states
    )
