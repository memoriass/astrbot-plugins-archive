from __future__ import annotations

import math
import re
import time
from typing import Any

from .sqlite_store import RuntimeStorageMixin

PREFERENCE_SCOPE_MIKAN_GROUP = "mikan_group"


class PluginPreferenceMixin(RuntimeStorageMixin):
    def preference_mode(self) -> str:
        value = str(self._cfg("preference_mode", "rank") or "rank").strip().lower()
        return value if value in {"off", "rank", "auto"} else "rank"

    def preference_min_uses(self) -> int:
        try:
            return max(int(self._cfg("preference_min_uses", 3)), 1)
        except (TypeError, ValueError):
            return 3

    def record_mikan_group_preference(self, origin: str, group: dict[str, Any]) -> None:
        if self.preference_mode() == "off":
            return
        label = _normalize_text(group.get("label"))
        if label:
            self.runtime_store().record_preference(
                origin=origin,
                scope=PREFERENCE_SCOPE_MIKAN_GROUP,
                key="label",
                value=label,
                payload={"display": str(group.get("label") or "")},
            )
        for language in _language_values(group):
            self.runtime_store().record_preference(
                origin=origin,
                scope=PREFERENCE_SCOPE_MIKAN_GROUP,
                key="language",
                value=language,
                payload={"display": language},
            )

    def reject_mikan_group_preference(self, origin: str, group: dict[str, Any]) -> None:
        if self.preference_mode() == "off":
            return
        label = _normalize_text(group.get("label"))
        if label:
            self.runtime_store().reject_preference(
                origin=origin,
                scope=PREFERENCE_SCOPE_MIKAN_GROUP,
                key="label",
                value=label,
                payload={"display": str(group.get("label") or "")},
            )
        for language in _language_values(group):
            self.runtime_store().reject_preference(
                origin=origin,
                scope=PREFERENCE_SCOPE_MIKAN_GROUP,
                key="language",
                value=language,
                payload={"display": language},
            )

    def rank_mikan_groups_by_preferences(
        self,
        origin: str,
        groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if self.preference_mode() == "off" or not groups:
            return groups

        preferences = self.runtime_store().list_preferences(
            origin=origin,
            scope=PREFERENCE_SCOPE_MIKAN_GROUP,
        )
        label_scores = _preference_score_map(preferences, "label")
        language_scores = _preference_score_map(preferences, "language")
        if not label_scores and not language_scores:
            return groups

        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index, group in enumerate(groups):
            copied = dict(group)
            score = label_scores.get(_normalize_text(copied.get("label")), 0.0) * 10
            for language in _language_values(copied):
                score += language_scores.get(language, 0.0) * 2
            if score > 0:
                copied["_preference_score"] = round(score, 3)
            ranked.append((score, index, copied))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked]

    def should_auto_select_mikan_group(
        self,
        origin: str,
        groups: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if self.preference_mode() != "auto" or not groups:
            return None
        preferences = self.runtime_store().list_preferences(
            origin=origin,
            scope=PREFERENCE_SCOPE_MIKAN_GROUP,
        )
        label_counts = {
            str(item.get("value") or ""): int(item.get("count") or 0)
            for item in preferences
            if item.get("key") == "label"
        }
        label_rejections = {
            str(item.get("value") or ""): int(item.get("rejected_count") or 0)
            for item in preferences
            if item.get("key") == "label"
        }
        top = groups[0]
        top_label = _normalize_text(top.get("label"))
        if label_counts.get(top_label, 0) < self.preference_min_uses():
            return None
        if label_rejections.get(top_label, 0) >= label_counts.get(top_label, 0):
            return None
        runner = groups[1] if len(groups) > 1 else {}
        top_score = float(top.get("_preference_score") or 0)
        runner_score = float(runner.get("_preference_score") or 0)
        if runner_score and runner_score >= top_score * 0.8:
            return None
        return top


def _preference_score_map(preferences: list[dict[str, Any]], key: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    now = time.time()
    for item in preferences:
        if item.get("key") != key:
            continue
        value = str(item.get("value") or "")
        count = int(item.get("count") or 0)
        rejected = int(item.get("rejected_count") or 0)
        if value and (count > 0 or rejected > 0):
            age_days = max((now - float(item.get("updated_at") or now)) / 86400, 0.0)
            recency = 1.0 / (1.0 + age_days / 45.0)
            positive = (1.0 + math.log(max(count, 1))) * recency if count > 0 else 0.0
            penalty = math.log1p(rejected) * 1.20
            score = max(positive - penalty, 0.0)
            scores[value] = max(scores.get(value, 0.0), score)
    return scores


def _language_values(group: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    parts = [str(group.get("label") or "")]
    tags = group.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    text = " ".join(parts).lower()
    if re.search(r"(?<![a-z])(?:chs|gb|sc|zh-hans)(?![a-z])|简|简中", text):
        values.add("简中")
    if re.search(r"(?<![a-z])(?:cht|big5|tc|zh-hant)(?![a-z])|繁|繁中", text):
        values.add("繁中")
    if re.search(r"(?<![a-z])(?:jp|jpn|japanese)(?![a-z])|日语", text):
        values.add("日语")
    if re.search(r"(?<![a-z])(?:eng|english)(?![a-z])|英语", text):
        values.add("英语")
    return values


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    return text
