from __future__ import annotations

import time
from typing import Any


COUNTER_KEYS = (
    "uid",
    "current_subscription",
    "alias",
    "shared_alias",
    "ambiguous",
    "miss",
    "bili_search",
    "error",
)


def record_resolver_event(
    plugin: Any,
    outcome: str,
    *,
    source: str = "",
    confidence: float = 0.0,
) -> None:
    stats = _stats(plugin)
    counters = stats.setdefault("counters", {})
    key = outcome if outcome in COUNTER_KEYS else "error"
    counters[key] = int(counters.get(key) or 0) + 1
    stats["last_event"] = {
        "outcome": key,
        "source": source,
        "confidence": round(float(confidence or 0), 4),
        "at": int(time.time()),
    }


def format_resolver_stats(plugin: Any) -> str:
    stats = _stats(plugin)
    counters = stats.get("counters") or {}
    attempts = sum(int(counters.get(key) or 0) for key in (
        "uid",
        "current_subscription",
        "alias",
        "shared_alias",
        "ambiguous",
        "miss",
        "error",
    ))
    if attempts <= 0 and not counters.get("bili_search"):
        return "- 解析统计：尚无解析记录"

    hits = sum(int(counters.get(key) or 0) for key in (
        "uid",
        "current_subscription",
        "alias",
        "shared_alias",
    ))
    fallback = int(counters.get("bili_search") or 0)
    parts = [
        f"- 解析统计：命中 {hits}/{attempts or hits}",
        f"当前订阅 {int(counters.get('current_subscription') or 0)}",
        f"历史别名 {int(counters.get('alias') or 0)}",
        f"共享别名 {int(counters.get('shared_alias') or 0)}",
        f"UID {int(counters.get('uid') or 0)}",
        f"搜索回退 {fallback}",
        f"歧义 {int(counters.get('ambiguous') or 0)}",
        f"未命中 {int(counters.get('miss') or 0)}",
    ]
    errors = int(counters.get("error") or 0)
    if errors:
        parts.append(f"异常 {errors}")
    return "；".join(parts)


def _stats(plugin: Any) -> dict:
    stats = getattr(plugin, "workflow_resolver_stats", None)
    if not isinstance(stats, dict):
        stats = {"counters": {}}
        setattr(plugin, "workflow_resolver_stats", stats)
    stats.setdefault("counters", {})
    return stats
