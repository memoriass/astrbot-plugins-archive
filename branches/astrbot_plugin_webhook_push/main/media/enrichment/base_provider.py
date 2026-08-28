"""
媒体数据丰富提供者基础接口
定义了媒体数据丰富和图片获取的标准接口
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from astrbot.api import logger


class MediaEnrichmentProvider(ABC):
    """媒体数据丰富提供者基础接口"""

    @abstractmethod
    async def enrich_media_data(self, media_data: dict) -> dict:
        """
        丰富媒体数据

        Args:
            media_data: 原始媒体数据

        Returns:
            丰富后的媒体数据
        """
        pass

    @abstractmethod
    async def get_media_image(self, media_data: dict) -> str:
        """
        获取媒体图片

        Args:
            media_data: 媒体数据

        Returns:
            图片URL，如果获取失败返回空字符串
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级，数字越小优先级越高"""
        pass


class MediaImageProvider(ABC):
    """媒体图片提供者基础接口"""

    @abstractmethod
    async def get_image(self, media_data: dict) -> str:
        """
        获取媒体图片

        Args:
            media_data: 媒体数据

        Returns:
            图片URL，如果获取失败返回空字符串
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级，数字越小优先级越高"""
        pass


class BaseProvider:
    """提供通用的 HTTP 请求及缓存逻辑"""

    def __init__(self, cache_ttl: int = 3600, request_interval: float = 0.5):
        self.cache: dict[str, Any] = {}
        self.cache_timestamps: dict[str, float] = {}
        self.cache_ttl = cache_ttl
        self.last_request_time = 0
        self.request_interval = request_interval

    async def _http_get(
        self, url: str, params: dict | None = None, headers: dict | None = None
    ) -> dict | None:
        """封装 aiohttp GET 请求，带频率限制"""
        await self._rate_limit()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=10
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return None
                    else:
                        logger.warning(f"HTTP GET {url} 失败: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"HTTP 请求异常 ({url}): {e}")
            return None

    def _get_from_cache(self, key: str) -> Any | None:
        if key in self.cache_timestamps:
            if time.time() - self.cache_timestamps[key] < self.cache_ttl:
                return self.cache.get(key)
            else:
                self.cache.pop(key, None)
                self.cache_timestamps.pop(key, None)
        return None

    def _set_cache(self, key: str, value: Any):
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()

    async def _rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_interval:
            await asyncio.sleep(self.request_interval - elapsed)
        self.last_request_time = time.time()
