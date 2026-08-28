from __future__ import annotations

from typing import Any


async def fetch_mikan_search(
    plugin: Any,
    text: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cached = getattr(plugin, "cached_mikan_search", None)
    if callable(cached):
        return await cached(text, payload)
    return await plugin.client(require_api_key=True).mikan_search(text, payload)


async def fetch_mikan_groups(plugin: Any, url: str) -> list[dict[str, Any]]:
    cached = getattr(plugin, "cached_mikan_groups", None)
    if callable(cached):
        return await cached(url)
    return await plugin.client(require_api_key=True).mikan_groups(url)
