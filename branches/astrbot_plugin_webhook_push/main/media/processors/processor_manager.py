"""
媒体处理器管理器
负责管理和调度不同的媒体处理器
"""

from typing import Any

from astrbot.api import logger

from .base_processor import BaseMediaProcessor
from .emby_processor import EmbyProcessor
from .generic_processor import GenericProcessor
from .jellyfin_processor import JellyfinProcessor
from .plex_processor import PlexProcessor


class ProcessorManager:
    """媒体处理器管理器"""

    def __init__(self):
        # 初始化所有处理器，按优先级排序
        self.processors: list[BaseMediaProcessor] = [
            EmbyProcessor(),
            JellyfinProcessor(),
            PlexProcessor(),
            GenericProcessor(),  # 通用处理器放在最后
        ]

        logger.info("媒体处理器管理器初始化完成")
        logger.info(f"已注册处理器: {[p.__class__.__name__ for p in self.processors]}")

    def detect_source(self, data: dict, headers: dict | None = None) -> str:
        """检测数据源类型"""
        try:
            for processor in self.processors:
                if processor.can_handle(data, headers):
                    source_name = processor.get_source_name()
                    logger.debug(f"检测到数据源: {source_name}")
                    return source_name

            logger.warning("未能检测到数据源，使用通用处理器")
            return "generic"

        except Exception as e:
            logger.error(f"数据源检测失败: {e}")
            return "generic"

    def get_processor(self, source: str) -> BaseMediaProcessor | None:
        """根据源类型获取对应的处理器"""
        processor_map = {
            "emby": EmbyProcessor,
            "jellyfin": JellyfinProcessor,
            "plex": PlexProcessor,
            "generic": GenericProcessor,
        }

        processor_class = processor_map.get(source.lower())
        if processor_class:
            return processor_class()

        logger.warning(f"未找到源 '{source}' 的处理器，使用通用处理器")
        return GenericProcessor()

    def convert_to_standard(
        self, data: dict, source: str = None, headers: dict | None = None
    ) -> dict:
        """将数据转换为标准格式"""
        try:
            # 如果没有指定源，自动检测
            if not source:
                source = self.detect_source(data, headers)

            # 获取对应的处理器
            processor = self.get_processor(source)
            if not processor:
                logger.error(f"无法获取源 '{source}' 的处理器")
                return {}

            logger.debug(f"使用 {processor.__class__.__name__} 处理数据")

            # 转换数据
            result = processor.convert_to_standard(data, headers)

            if not result:
                logger.warning(f"{source} 数据转换失败")
                return {}

            # 验证转换结果
            if not processor.validate_standard_data(result):
                logger.error(f"{source} 数据验证失败")
                return {}

            logger.info(f"{source} 数据转换成功")
            return result

        except Exception as e:
            logger.error(f"数据转换处理出错: {e}")
            logger.debug(f"数据转换失败详情: {e}", exc_info=True)
            return {}

    def get_processor_info(self) -> dict[str, Any]:
        """获取处理器信息"""
        info = {"total_processors": len(self.processors), "processors": []}

        for processor in self.processors:
            processor_info = {
                "name": processor.__class__.__name__,
                "source_name": processor.get_source_name(),
                "description": processor.__doc__ or "无描述",
            }
            info["processors"].append(processor_info)

        return info

    def test_processor(
        self, source: str, test_data: dict, headers: dict | None = None
    ) -> dict[str, Any]:
        """测试指定处理器"""
        try:
            processor = self.get_processor(source)
            if not processor:
                return {"success": False, "error": f"未找到源 '{source}' 的处理器"}

            # 测试检测能力
            can_handle = processor.can_handle(test_data, headers)

            # 测试转换能力
            result = {}
            conversion_success = False
            if can_handle:
                result = processor.convert_to_standard(test_data, headers)
                conversion_success = bool(
                    result and processor.validate_standard_data(result)
                )

            return {
                "success": True,
                "processor": processor.__class__.__name__,
                "source_name": processor.get_source_name(),
                "can_handle": can_handle,
                "conversion_success": conversion_success,
                "result": result,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_processor(self, processor: BaseMediaProcessor, priority: int = None):
        """添加自定义处理器"""
        if not isinstance(processor, BaseMediaProcessor):
            raise ValueError("处理器必须继承自BaseMediaProcessor")

        if priority is None:
            # 添加到通用处理器之前
            self.processors.insert(-1, processor)
        else:
            self.processors.insert(priority, processor)

        logger.info(f"已添加自定义处理器: {processor.__class__.__name__}")

    def remove_processor(self, processor_name: str) -> bool:
        """移除指定处理器"""
        for i, processor in enumerate(self.processors):
            if processor.__class__.__name__ == processor_name:
                self.processors.pop(i)
                logger.info(f"已移除处理器: {processor_name}")
                return True

        logger.warning(f"未找到处理器: {processor_name}")
        return False
