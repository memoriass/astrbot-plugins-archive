from __future__ import annotations

import re
from collections.abc import Iterable

from astrbot.api.provider import Provider

_TOPIC_PATTERN = re.compile(r"<([^<>]{1,40})>")


class LLMKeywordExtractor:
    """Extract concept keywords and topic summaries with an AstrBot provider."""

    def __init__(self, max_keywords: int = 5):
        self.max_keywords = max(1, min(max_keywords, 5))

    def select_provider(self, providers: Iterable[Provider]) -> Provider | None:
        """Return the first available chat provider from an iterable."""
        for provider in providers:
            if provider is not None:
                return provider
        return None

    def keyword_target_count(self, text: str) -> int:
        """Choose a keyword count based on text length."""
        length = len(text.strip())
        if length <= 12:
            return 2
        if length <= 20:
            return 3
        if length <= 30:
            return 4
        return 5

    async def extract_keywords(
        self,
        text: str,
        provider: Provider | None,
    ) -> list[str]:
        """Extract 1-5 concept keywords in <topic> format."""
        content = text.strip()
        if not content or provider is None:
            return []
        target = min(self.keyword_target_count(content), self.max_keywords)
        response = await provider.text_chat(
            prompt=self._keyword_prompt(content, target),
            system_prompt=(
                "You extract concept keywords from chat text. "
                "Return only comma-separated topics in <topic> format."
            ),
        )
        return self._parse_keywords(
            str(getattr(response, "completion_text", "") or ""),
            target,
        )

    async def extract_keywords_from_providers(
        self,
        text: str,
        providers: Iterable[Provider],
    ) -> list[str]:
        """Select a provider and extract keywords from text."""
        return await self.extract_keywords(text, self.select_provider(providers))

    async def summarize_topic(
        self,
        text: str,
        topic: str,
        provider: Provider | None,
    ) -> str:
        """Summarize what the text says about one topic."""
        content = text.strip()
        cleaned_topic = self._clean_topic(topic)
        if not content or not cleaned_topic or provider is None:
            return ""
        response = await provider.text_chat(
            prompt=self._summary_prompt(content, cleaned_topic),
            system_prompt=(
                "You summarize a single target topic from chat text. "
                "Return one concise sentence only."
            ),
        )
        return self._clean_summary(str(getattr(response, "completion_text", "") or ""))

    async def integrate_memory(
        self,
        old_memory: str,
        new_memory: str,
        provider: Provider | None,
    ) -> str:
        """Merge old and new memory texts for the same concept using LLM.

        Falls back to simple concatenation on failure or missing provider.
        """
        old = old_memory.strip()
        new = new_memory.strip()
        if not old:
            return new[:4000]
        if not new or new in old:
            return old[:4000]
        if provider is None:
            return f"{old} | {new}"[:4000]
        try:
            response = await provider.text_chat(
                prompt=self._integrate_prompt(old, new),
                system_prompt=(
                    "You merge two memory fragments about the same concept. "
                    "Return a single concise paragraph preserving all key facts. "
                    "Do not explain or add commentary."
                ),
            )
            merged = self._clean_summary(
                str(getattr(response, "completion_text", "") or "")
            )
            return merged[:4000] if merged else f"{old} | {new}"[:4000]
        except Exception:  # noqa: BLE001
            return f"{old} | {new}"[:4000]

    def _integrate_prompt(self, old_memory: str, new_memory: str) -> str:
        return (
            "Merge the following two memory fragments about the same concept "
            "into one concise paragraph.\n"
            "Rules:\n"
            "1. Preserve all concrete facts from both fragments.\n"
            "2. Remove duplicates.\n"
            "3. Keep it concise (one paragraph).\n"
            "4. Do not add any commentary.\n"
            f"Old memory:\n{old_memory[:1600]}\n\n"
            f"New memory:\n{new_memory[:800]}"
        )

    def _keyword_prompt(self, text: str, target: int) -> str:
        return (
            f"Extract {target} concept keywords from the text below.\n"
            "Rules:\n"
            "1. Output only comma-separated items.\n"
            "2. Use <topic> format for every item.\n"
            "3. Use short concept nouns or noun phrases.\n"
            "4. Do not explain anything.\n"
            f"Text:\n{text[:1200]}"
        )

    def _summary_prompt(self, text: str, topic: str) -> str:
        return (
            "Summarize the information about the target topic from the text below.\n"
            "Rules:\n"
            "1. Keep one concise sentence.\n"
            "2. Preserve concrete facts when present.\n"
            "3. Do not mention unrelated topics.\n"
            f"Target topic: <{topic}>\n"
            f"Text:\n{text[:1600]}"
        )

    def _parse_keywords(self, raw: str, limit: int) -> list[str]:
        topics = [self._clean_topic(match) for match in _TOPIC_PATTERN.findall(raw)]
        if not topics:
            parts = raw.replace("\n", ",").split(",")
            topics = [self._clean_topic(part) for part in parts]
        deduped: list[str] = []
        seen: set[str] = set()
        for topic in topics:
            if not topic or topic in seen:
                continue
            seen.add(topic)
            deduped.append(topic)
            if len(deduped) >= limit:
                break
        return deduped

    def _clean_topic(self, topic: str) -> str:
        cleaned = topic.strip().strip("<>").strip("`'\" ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:40]

    async def select_relevant_concepts(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        provider: Provider | None,
        max_select: int = 4,
    ) -> list[str]:
        """Two-stage LLM memory selection.

        Given a user query and a list of (concept, memory_snippet) candidates,
        ask the LLM which concepts are relevant. Returns a list of selected
        concept names (at most *max_select*).  Falls back to returning all
        candidate concepts if LLM call fails.
        """
        if not query.strip() or not candidates or provider is None:
            return [c for c, _ in candidates[:max_select]]
        # Build candidate list with random-ish IDs to reduce positional bias.
        import random as _rng

        indices = list(range(len(candidates)))
        _rng.shuffle(indices)
        id_map: dict[int, str] = {}
        lines: list[str] = []
        for display_idx, real_idx in enumerate(indices, start=1):
            concept, snippet = candidates[real_idx]
            short = snippet.replace("\n", " ")[:100]
            lines.append(f"{display_idx}. [{concept}] {short}")
            id_map[display_idx] = concept
        memory_info = "\n".join(lines)
        prompt = (
            "根据用户当前的消息，从下方记忆候选中选出与之相关的编号。\n"
            f"用户消息：{query[:300]}\n\n"
            f"记忆候选：\n{memory_info}\n\n"
            "请只输出相关的编号，用逗号分隔，例如 1,3,5。\n"
            "如果都不相关就输出 none。"
        )
        try:
            response = await provider.text_chat(
                prompt=prompt,
                system_prompt="你是记忆筛选助手。只输出编号列表，不要解释。",
            )
            raw = str(getattr(response, "completion_text", "") or "")
            return self._parse_selected_ids(raw, id_map, max_select)
        except Exception:  # noqa: BLE001
            return [c for c, _ in candidates[:max_select]]

    def _parse_selected_ids(
        self,
        raw: str,
        id_map: dict[int, str],
        max_select: int,
    ) -> list[str]:
        """Parse LLM output like '1,3,5' into concept names."""
        if "none" in raw.lower():
            return []
        selected: list[str] = []
        seen: set[str] = set()
        for part in re.split(r"[,，\s]+", raw):
            part = part.strip().strip(".")
            if not part.isdigit():
                continue
            idx = int(part)
            concept = id_map.get(idx)
            if concept and concept not in seen:
                seen.add(concept)
                selected.append(concept)
                if len(selected) >= max_select:
                    break
        return selected

    def _clean_summary(self, text: str) -> str:
        summary = re.sub(r"\s+", " ", text.strip().strip("`'\" "))
        return summary[:280]
