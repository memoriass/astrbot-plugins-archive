"""
适配器类型定义和工厂类
"""

from typing import Any

from .adapter_base import AdapterType, BaseAdapter


class AdapterFactory:
    """适配器工厂类"""

    @staticmethod
    def create_adapter(platform_name: str) -> BaseAdapter:
        """
        根据平台名称创建适配器实例

        Args:
            platform_name: 平台名称

        Returns:
            适配器实例
        """
        # 导入适配器类（延迟导入避免循环依赖）
        from .aiocqhttp_adapter import AiocqhttpAdapter
        from .llonebot_adapter import LLOneBotAdapter
        from .napcat_adapter import NapCatAdapter

        # 根据平台名称自动推断适配器类型
        adapter_type = AdapterFactory._infer_adapter_type(platform_name)

        # 根据适配器类型创建实例
        if adapter_type == AdapterType.NAPCAT:
            return NapCatAdapter(platform_name)
        elif adapter_type == AdapterType.LLONEBOT:
            return LLOneBotAdapter(platform_name)
        else:
            # 默认使用 aiocqhttp 适配器
            return AiocqhttpAdapter(platform_name)

    @staticmethod
    def _infer_adapter_type(platform_name: str) -> str:
        """根据平台名称推断适配器类型"""
        platform_lower = platform_name.lower()

        if "napcat" in platform_lower:
            return AdapterType.NAPCAT
        elif "llonebot" in platform_lower:
            return AdapterType.LLONEBOT
        elif platform_lower in ["onebot"]:
            return AdapterType.NAPCAT  # onebot通常兼容napcat格式
        else:
            # 默认使用 aiocqhttp 适配器
            return AdapterType.AIOCQHTTP

    @staticmethod
    def get_supported_types() -> list[str]:
        """获取支持的适配器类型列表"""
        return [
            AdapterType.NAPCAT,
            AdapterType.LLONEBOT,
            AdapterType.AIOCQHTTP,
        ]

    @staticmethod
    def get_adapter_info(adapter_type: str) -> dict[str, Any]:
        """获取适配器信息"""
        info_map = {
            AdapterType.NAPCAT: {
                "name": "NapCat",
                "description": "支持NapCat协议的合并转发适配器",
                "features": ["send_forward_msg", "群聊合并转发", "私聊合并转发"],
            },
            AdapterType.LLONEBOT: {
                "name": "LLOneBot",
                "description": "支持LLOneBot协议的合并转发适配器",
                "features": ["合并转发", "自定义发送者信息"],
            },
            AdapterType.AIOCQHTTP: {
                "name": "AiocqhttpOptimized",
                "description": "优化的aiocqhttp适配器，支持AstrBot原生组件和消息验证",
                "features": [
                    "AstrBot原生Node组件",
                    "消息发送验证",
                    "降级兼容",
                    "群聊私聊支持",
                ],
            },
        }
        return info_map.get(
            adapter_type,
            {"name": "Unknown", "description": "未知适配器类型", "features": []},
        )
