"""
消息适配器模块

该模块包含了各种协议端的消息适配器实现，用于处理不同协议的消息发送。
适配器模块与媒体处理器分离，便于独立维护和扩展。

支持的适配器类型：
- NapCat: 支持 NapCat 协议的合并转发适配器
- LLOneBot: 支持 LLOneBot 协议的合并转发适配器
- AiocqhttpOptimized: 优化的 aiocqhttp 适配器，支持 AstrBot 原生组件（默认）

使用示例：
    from adapters import AdapterFactory, AdapterType

    # 创建适配器实例
    adapter = AdapterFactory.create_adapter("napcat")

    # 发送合并转发消息
    result = await adapter.send_forward_messages(
        bot_client, group_id, messages
    )
"""

from .adapter_base import AdapterType, BaseAdapter
from .adapter_factory import AdapterFactory
from .aiocqhttp_adapter import AiocqhttpAdapter
from .llonebot_adapter import LLOneBotAdapter
from .napcat_adapter import NapCatAdapter

__all__ = [
    "BaseAdapter",
    "AdapterType",
    "AdapterFactory",
    "NapCatAdapter",
    "LLOneBotAdapter",
    "AiocqhttpAdapter",
]

__version__ = "1.0.0"
