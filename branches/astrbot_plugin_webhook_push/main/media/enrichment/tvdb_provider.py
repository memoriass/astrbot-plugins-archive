"""
TVDB 媒体数据提供者
提供 TheTVDB API 的媒体数据丰富功能
"""

import time
from typing import Any

from astrbot.api import logger

from .base_provider import BaseProvider, MediaEnrichmentProvider, MediaImageProvider


class TVDBProvider(MediaEnrichmentProvider, MediaImageProvider, BaseProvider):
    """TVDB 媒体数据提供者"""

    def __init__(self, api_key: str = ""):
        BaseProvider.__init__(self, request_interval=0.2)
        self.api_key = api_key
        self.base_url = "https://api4.thetvdb.com/v4"

        # 认证信息
        self.jwt_token = ""
        self.token_expires = 0

    @property
    def name(self) -> str:
        return "TVDB"

    @property
    def priority(self) -> int:
        return 2  # TVDB 作为辅助数据源

    async def enrich_media_data(self, media_data: dict) -> dict:
        """使用 TVDB API 丰富媒体数据"""
        try:
            if not self.api_key:
                return media_data

            item_type = media_data.get("item_type", "")
            if item_type != "Episode":
                return media_data

            series_name = media_data.get("series_name", "")
            season = media_data.get("season_number")
            episode = media_data.get("episode_number")

            if not all([series_name, season, episode]):
                return media_data

            # 优先尝试 ProviderIDs 中的 TVDB ID
            p_ids = media_data.get("provider_ids", {})
            tvdb_id = p_ids.get("TVDB") or p_ids.get("Tvdb")

            logger.info(
                f"开始 TVDB 数据丰富: {series_name} (ID: {tvdb_id or 'Searching...'})"
            )

            await self._authenticate()
            if not self.jwt_token:
                return media_data

            if not tvdb_id:
                series_info = await self._search_series(series_name)
                if series_info:
                    tvdb_id = series_info.get("tvdb_id")

            if tvdb_id:
                ep_details = await self._get_episode_details(tvdb_id, season, episode)
                if ep_details:
                    media_data.update(
                        {
                            "tvdb_enriched": True,
                            "tvdb_series_id": tvdb_id,
                            "overview": ep_details.get("overview")
                            or media_data.get("overview"),
                            "item_name": ep_details.get("name")
                            or media_data.get("item_name"),
                        }
                    )

            return media_data

        except Exception as e:
            logger.error(f"TVDB 数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        return await self.get_image(media_data)

    async def get_image(self, media_data: dict) -> str:
        try:
            series_name = media_data.get("series_name", "")
            if not series_name:
                return ""
                
            await self._authenticate()
            if not self.jwt_token:
                return ""

            series_info = await self._search_series(series_name)
            if series_info and series_info.get("image"):
                return series_info.get("image")
            return ""
        except Exception:
            return ""

    # --- 私有方法 ---

    async def _authenticate(self):
        """TVDB V4 认证"""
        if self.jwt_token and time.time() < self.token_expires:
            return

        if not self.api_key:
            return

        auth_url = f"{self.base_url}/login"
        auth_data = {"apikey": self.api_key}

        # 直接使用 aiohttp 避免 BaseProvider 的频率限制逻辑，因为这是初始化请求
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, json=auth_data) as response:
                    if response.status == 200:
                        res_json = await response.json()
                        self.jwt_token = res_json.get("data", {}).get("token", "")
                        self.token_expires = time.time() + 24 * 3600 - 300
                        logger.info("TVDB 认证成功")
        except Exception as e:
            logger.error(f"TVDB 认证失败: {e}")

    async def _search_series(self, name: str) -> dict | None:
        cache_key = f"tvdb_search_{name}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        url = f"{self.base_url}/search"
        headers = {"Authorization": f"Bearer {self.jwt_token}"}
        params = {"query": name, "type": "series"}

        data = await self._http_get(url, params=params, headers=headers)
        if data and data.get("data"):
            series = data["data"][0]
            self._set_cache(cache_key, series)
            return series
        return None

    async def _get_episode_details(
        self, series_id: str, season: Any, episode: Any
    ) -> dict | None:
        cache_key = f"tvdb_ep_{series_id}_{season}_{episode}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # TVDB V4 剧集查询有专门的路由通常需要根据系列 ID 遍历或直接通过 ID，
        # 这里使用比较通用的搜索或详情接口，但 TVDB 接口较为复杂
        # 简单逻辑：通过 /series/{id}/episodes/default...
        url = f"{self.base_url}/series/{series_id}/episodes/default/zh-CN"
        headers = {"Authorization": f"Bearer {self.jwt_token}"}

        # 实际 API 可能需要处理分页，这里先简化处理
        data = await self._http_get(url, headers=headers)
        if data and data.get("data") and data["data"].get("episodes"):
            eps = data["data"]["episodes"]
            for ep in eps:
                if str(ep.get("seasonNumber")) == str(season) and str(
                    ep.get("number")
                ) == str(episode):
                    self._set_cache(cache_key, ep)
                    return ep
        return None
