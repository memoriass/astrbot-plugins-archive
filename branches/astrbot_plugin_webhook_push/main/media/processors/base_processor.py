"""
基础媒体处理器
定义所有媒体处理器的通用接口和功能
"""

import html
import re
from abc import ABC, abstractmethod
from typing import Any

from astrbot.api import logger


class BaseMediaProcessor(ABC):
    """基础媒体处理器抽象类"""

    def __init__(self):
        pass

    @abstractmethod
    def can_handle(self, data: dict, headers: dict | None = None) -> bool:
        """检查是否能处理该数据源"""
        pass

    @abstractmethod
    def convert_to_standard(self, data: dict, headers: dict | None = None) -> dict:
        """将数据转换为标准格式"""
        pass

    def get_source_name(self) -> str:
        """获取数据源名称"""
        return self.__class__.__name__.replace("Processor", "").lower()

    def clean_text(self, text: str) -> str:
        """清理文本内容"""
        if not text:
            return ""

        # HTML 解码
        text = html.unescape(text)

        # 移除多余的空白字符
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def safe_get_runtime(self, runtime_ticks: Any) -> str:
        """安全地转换运行时间"""
        try:
            if (
                runtime_ticks
                and isinstance(runtime_ticks, (int, float))
                and runtime_ticks > 0
            ):
                # Emby/Jellyfin的RunTimeTicks是以100纳秒为单位
                # 1秒 = 10,000,000 ticks，1分钟 = 600,000,000 ticks
                runtime_minutes = int(runtime_ticks // 600000000)
                if runtime_minutes > 0:
                    return f"{runtime_minutes} 分钟"
            return ""
        except (TypeError, ValueError, ZeroDivisionError) as e:
            logger.debug(f"时长转换失败: {e}, runtime_ticks={runtime_ticks}")
            return ""

    def get_media_type_display(self, item_type: str) -> str:
        """获取媒体类型的显示名称"""
        # 简单的类型映射
        type_map = {
            "Movie": "电影",
            "Series": "剧集",
            "Episode": "剧集",
            "Season": "季",
            "Audio": "音频",
            "MusicVideo": "音乐视频",
        }
        return type_map.get(item_type, item_type)

    def create_standard_data(self, **kwargs) -> dict:
        """创建标准格式的数据"""
        return {
            "item_type": kwargs.get("item_type", "Unknown"),
            "series_name": kwargs.get("series_name", ""),
            "item_name": kwargs.get("item_name", ""),
            "season_number": str(kwargs.get("season_number", ""))
            if kwargs.get("season_number")
            else "",
            "episode_number": str(kwargs.get("episode_number", ""))
            if kwargs.get("episode_number")
            else "",
            "year": str(kwargs.get("year", "")) if kwargs.get("year") else "",
            "overview": kwargs.get("overview", ""),
            "runtime": kwargs.get("runtime", ""),
            "image_url": kwargs.get("image_url", ""),
            "source_data": kwargs.get("source_data", self.get_source_name()),
        }

    def validate_standard_data(self, data: dict) -> bool:
        """验证标准格式数据的有效性"""
        # 检查是否有基本的名称信息（确保不是空字符串）
        series_name = data.get("series_name", "").strip()
        item_name = data.get("item_name", "").strip()

        if not (series_name or item_name):
            logger.error("媒体数据缺少名称信息")
            logger.debug(f"series_name: '{series_name}', item_name: '{item_name}'")
            return False

        return True
