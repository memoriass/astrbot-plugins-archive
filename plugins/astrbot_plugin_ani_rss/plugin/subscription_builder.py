from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..integrations.ani_rss import AniRssError


class SubscriptionBuilderMixin:
    def _resolve_type(self, rss_url: str, rss_type: str = "") -> str:
        rss_type = (rss_type or "").strip()
        if rss_type and rss_type != "auto":
            return rss_type

        host = urlparse(rss_url).netloc.lower()
        if "mikan" in host:
            return "mikan"
        return "other"

    async def _resolve_mikan_bgm_url(self, rss_url: str) -> str:
        bangumi_id = ""
        parsed = urlparse(rss_url)
        query = parse_qs(parsed.query)
        if query.get("bangumiId"):
            bangumi_id = str(query["bangumiId"][0]).strip()
        if not bangumi_id:
            match = re.search(r"/Bangumi/(\d+)", rss_url)
            bangumi_id = match.group(1) if match else ""
        if not bangumi_id:
            return ""
        try:
            cached = getattr(self, "cached_mikan_search", None)
            if callable(cached):
                data = await cached(f"bangumiId: {bangumi_id}")
            else:
                data = await self.client(require_api_key=True).mikan_search(f"bangumiId: {bangumi_id}")
        except Exception:
            return ""
        for section in data.get("weeks") or data.get("items") or []:
            if not isinstance(section, dict):
                continue
            for item in section.get("items") or []:
                if isinstance(item, dict) and item.get("bgmUrl"):
                    return str(item["bgmUrl"]).strip()
        return ""

    async def build_subscription(
        self,
        *,
        rss_url: str,
        rss_type: str = "",
        bgm_url: str = "",
        subgroup: str = "",
        enable: bool | None = None,
    ) -> dict[str, Any]:
        rss_url = rss_url.strip()
        if not rss_url:
            raise AniRssError("rss_url is required.")

        resolved_type = self._resolve_type(rss_url, rss_type)
        if resolved_type == "mikan" and not bgm_url.strip():
            bgm_url = await self._resolve_mikan_bgm_url(rss_url)
        if resolved_type == "other" and not bgm_url.strip():
            raise AniRssError("bgm_url is required when rss_type is other.")

        actual_enable = True if enable is None else bool(enable)
        ani = await self.client(require_api_key=True).rss_to_ani(
            rss_url=rss_url,
            rss_type=resolved_type,
            bgm_url=bgm_url,
            subgroup=subgroup,
            enable=actual_enable,
        )
        if subgroup.strip():
            ani["subgroup"] = subgroup.strip()
        if bgm_url.strip() and not ani.get("bgmUrl"):
            ani["bgmUrl"] = bgm_url.strip()
        return ani
