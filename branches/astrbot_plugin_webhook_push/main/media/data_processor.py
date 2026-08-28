"""
媒体数据处理器
负责媒体数据的检测、处理、去重等功能
"""

import hashlib
import json
import time

from astrbot.api import logger

from .media_handler import MediaHandler


class MediaDataProcessor:
    """媒体数据处理器"""

    def __init__(self, media_handler: MediaHandler, cache_ttl_seconds: int = 300):
        self.media_handler = media_handler
        self.cache_ttl_seconds = cache_ttl_seconds
        self.request_cache: dict[str, float] = {}

    def is_duplicate_request(self, media_data: dict) -> bool:
        """检查是否为重复请求 - 使用哈希校验，排除图片以保持更高准确率"""
        request_hash = self.calculate_request_hash(media_data)
        if not request_hash:
            return False

        current_time = time.time()

        # 清理过期缓存
        self.cleanup_expired_cache(current_time)

        # 检查是否重复
        if request_hash in self.request_cache:
            cached_time = self.request_cache[request_hash]
            logger.debug(
                f"检测到重复请求，哈希: {request_hash[:8]}..., 缓存时间: {cached_time}"
            )
            return True

        # 缓存新请求
        self.request_cache[request_hash] = current_time + self.cache_ttl_seconds
        logger.debug(
            f"缓存新请求，哈希: {request_hash[:8]}..., 过期时间: {current_time + self.cache_ttl_seconds}"
        )
        return False

    def calculate_request_hash(self, media_data: dict) -> str:
        """计算请求哈希值 - 排除图片和不稳定字段以提高准确率"""
        try:
            return self.calculate_standard_hash(media_data)
        except Exception as e:
            logger.error(f"计算请求哈希失败: {e}")
            return ""

    def calculate_standard_hash(self, media_data: dict) -> str:
        """计算标准媒体数据的哈希值"""
        # 排除不稳定字段
        stable_fields = {
            k: v
            for k, v in media_data.items()
            if k not in ["image_url", "timestamp", "runtime_ticks"]
        }
        hash_string = json.dumps(stable_fields, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    def cleanup_expired_cache(self, current_time: float):
        """清理过期缓存"""
        expired_keys = [
            key
            for key, expire_time in self.request_cache.items()
            if current_time > expire_time
        ]
        for key in expired_keys:
            del self.request_cache[key]

        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 个过期缓存条目")

    async def detect_and_process_raw_data(self, raw_msg: dict) -> dict | None:
        """检测和处理原始数据"""
        try:
            body_text = raw_msg.get("raw_data", "")
            headers = raw_msg.get("headers", {})

            # 处理 Plex 的 multipart/form-data 特殊情况
            if (
                "multipart/form-data" in headers.get("Content-Type", "").lower()
                or "plex" in headers.get("User-Agent", "").lower()
            ):
                # Plex 默认将 JSON 放在 form-data 的 'payload' 字段中
                # 简单检测方法：如果 body_text 看起来像 multipart (包含 boundary)
                if 'name="payload"' in body_text:
                    try:
                        # 尝试正则匹配提取 payload 部分
                        import re

                        match = re.search(
                            r'name="payload"\r\n\r\n(\{.*?\})\r\n', body_text, re.DOTALL
                        )
                        if match:
                            body_text = match.group(1)
                            logger.info("成功从 Plex Multipart 载荷中提取 JSON")
                    except Exception as e:
                        logger.warning(f"从 Plex Multipart 提取数据失败: {e}")

            # 处理标准媒体数据
            try:
                raw_data = json.loads(body_text)
                logger.debug(f"成功解析 Webhook JSON 数据: {str(raw_data)[:200]}...")
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析失败: {e}, 原始数据预览: {body_text[:200]}")
                return None

            # 检测媒体来源
            detected_source = self.media_handler.detect_media_source(raw_data, headers)
            if not detected_source:
                logger.warning("未识别的媒体数据格式")
                return None

            logger.info(f"检测到媒体来源: {detected_source}")

            # 使用媒体处理器处理数据
            media_data = await self.media_handler.process_media_data(
                raw_data, detected_source, headers
            )

            # 验证处理结果
            if not self.media_handler.validate_media_data(
                media_data.get("media_data", {})
            ):
                logger.error("媒体数据验证失败")
                return None

            # 检查重复请求
            if self.is_duplicate_request(media_data):
                logger.info("检测到重复请求，忽略")
                return None

            # 标记为媒体消息
            media_data["message_type"] = "media"
            return media_data

        except Exception as e:
            logger.error(f"原始数据检测和处理失败: {e}")
            return None
