from __future__ import annotations

import hashlib
import json
from typing import Any

from .sqlite_store import RuntimeStorageMixin

LIST_ANI_CACHE_KEY = "ani_rss:list_ani:v1"
MIKAN_SEARCH_CACHE_PREFIX = "ani_rss:mikan_search:v1:"
MIKAN_GROUP_CACHE_PREFIX = "ani_rss:mikan_group:v1:"


class PluginCacheMixin(RuntimeStorageMixin):
    async def cached_list_ani(self) -> list[dict[str, Any]]:
        ttl = self.subscription_cache_ttl_seconds()
        if ttl > 0:
            cached = self.runtime_store().get_cache(LIST_ANI_CACHE_KEY)
            if isinstance(cached, list):
                return [item for item in cached if isinstance(item, dict)]

        data = await self.client(require_api_key=True).list_ani()
        if ttl > 0:
            self.runtime_store().set_cache(LIST_ANI_CACHE_KEY, data, ttl)
        return data

    def invalidate_subscription_cache(self) -> None:
        self.runtime_store().delete_cache(LIST_ANI_CACHE_KEY)

    async def cached_mikan_search(
        self,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ttl = self.mikan_search_cache_ttl_seconds()
        cache_key = _cache_key(MIKAN_SEARCH_CACHE_PREFIX, text, payload or {})
        if ttl > 0:
            cached = self.runtime_store().get_cache(cache_key)
            if isinstance(cached, dict):
                return cached

        data = await self.client(require_api_key=True).mikan_search(text, payload)
        if ttl > 0:
            self.runtime_store().set_cache(cache_key, data, ttl)
        return data

    async def cached_mikan_groups(self, url: str) -> list[dict[str, Any]]:
        ttl = self.mikan_search_cache_ttl_seconds()
        cache_key = _cache_key(MIKAN_GROUP_CACHE_PREFIX, url)
        if ttl > 0:
            cached = self.runtime_store().get_cache(cache_key)
            if isinstance(cached, list):
                return [item for item in cached if isinstance(item, dict)]

        data = await self.client(require_api_key=True).mikan_groups(url)
        if ttl > 0:
            self.runtime_store().set_cache(cache_key, data, ttl)
        return data


def _cache_key(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"
