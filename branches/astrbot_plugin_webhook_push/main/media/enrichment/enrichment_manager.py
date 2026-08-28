"""
媒体数据丰富管理器
统一管理元数据提供者并集成自动翻译功能
"""

import os
import hashlib
from astrbot.api import logger

from ..cache_manager import CacheManager
from .tmdb_provider import TMDBProvider
from .tvdb_provider import TVDBProvider
from .bgm_provider import BGMProvider
from ...utils.translator import Translator

class EnrichmentManager:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.enrichment_providers = []
        self.image_providers = []

        # 1. 初始化持久化缓存
        db_dir = self.config.get("data_path")
        if not db_dir:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(root_dir, "data")

        persistence_days = self.config.get("cache_persistence_days", 7)
        self.cache = CacheManager(db_dir, persistence_days)
        self.cache.cleanup()

        # 2. 初始化翻译器
        self.translator = Translator(self.config)

        # 3. 初始化提供者
        self._initialize_providers()

    def _initialize_providers(self):
        """加载元数据提供者并排序"""
        enabled = []
        tmdb_key = self.config.get("tmdb_api_key")
        fanart_key = self.config.get("fanart_api_key")
        if tmdb_key:
            p = TMDBProvider(tmdb_key, fanart_key)
            self.enrichment_providers.append(p)
            self.image_providers.append(p)
            enabled.append("TMDB")

        tvdb_key = self.config.get("tvdb_api_key")
        if tvdb_key:
            p = TVDBProvider(tvdb_key)
            self.enrichment_providers.append(p)
            self.image_providers.append(p)
            enabled.append("TVDB")

        p = BGMProvider(self.config)
        self.enrichment_providers.append(p)
        self.image_providers.append(p)
        enabled.append("Bangumi")

        # 优先级: TMDB -> BGM -> TVDB
        order = {"TMDB": 0, "Bangumi": 1, "TVDB": 2}
        self.enrichment_providers.sort(key=lambda x: order.get(x.name, 99))
        self.image_providers.sort(key=lambda x: order.get(x.name, 99))
        logger.info(f"媒体提供者加载完成: {', '.join(enabled)}")

    async def enrich_media_data(self, media_data: dict) -> dict:
        """核心数据丰富流程，包含自动翻译"""
        try:
            # 1. 缓存优先
            key = self._generate_cache_key(media_data)
            cached = self.cache.get(key)
            if cached:
                media_data.update(cached)
                return media_data

            # 2. 依次尝试提供者
            enriched = False
            for provider in self.enrichment_providers:
                try:
                    res = await provider.enrich_media_data(media_data.copy())
                    if res != media_data:
                        media_data.update(res)
                        enriched = True
                        break 
                except: continue

            # 3. 自动翻译英文简介
            overview = media_data.get("overview")
            if overview:
                translated = await self.translator.translate(overview)
                if translated:
                    media_data["overview"] = translated

            # 4. 写入持久化缓存
            if enriched:
                fields = ["overview", "tmdb_id", "bgm_id", "tmdb_enriched", "bgm_enriched", "year", "poster_path"]
                cache_data = {k: media_data.get(k) for k in fields}
                self.cache.set(key, cache_data)

            return media_data
        except Exception as e:
            logger.error(f"数据丰富出错: {e}")
            return media_data

    async def get_media_image(self, media_data: dict) -> str:
        """获取媒体图片地址"""
        for provider in self.image_providers:
            try:
                url = await provider.get_image(media_data)
                if url: return url
            except: continue
        return ""

    def _generate_cache_key(self, media_data: dict) -> str:
        """生成缓存 Key"""
        p_ids = media_data.get("provider_ids", {})
        for platform in ["TMDB", "IMDB", "TVDB"]:
            id_val = p_ids.get(platform) or p_ids.get(platform.capitalize()) or p_ids.get(platform.lower())
            if id_val: return f"{platform}_{id_val}"
        
        raw_key = f"{media_data.get('item_name')}_{media_data.get('item_type')}_{media_data.get('year')}"
        return hashlib.md5(raw_key.encode()).hexdigest()

# 向后兼容别名
MediaEnrichmentManager = EnrichmentManager
