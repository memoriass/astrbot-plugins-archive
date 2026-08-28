"""
适配器基类
定义不同协议端的合并转发消息发送接口
"""

from abc import ABC, abstractmethod
from typing import Any

from astrbot.api import logger


class BaseAdapter(ABC):
    """协议端适配器基类"""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.logger = logger

    @abstractmethod
    async def send_forward_messages(
        self, bot_client: Any, group_id: str, messages: list[dict[str, Any]], **kwargs
    ) -> dict[str, Any]:
        """
        发送合并转发消息

        Args:
            bot_client: 协议端客户端实例
            group_id: 群组ID
            messages: 消息列表，每个消息包含 message_text 和可选的 image_url
            **kwargs: 其他参数

        Returns:
            发送结果字典，包含 success 和 message_id 等信息
        """
        pass

    @abstractmethod
    def build_forward_node(
        self,
        message: dict[str, Any],
        sender_id: str = "2659908767",
        sender_name: str = "媒体通知",
    ) -> dict[str, Any]:
        """
        构建单个转发节点

        Args:
            message: 消息内容字典
            sender_id: 发送者ID
            sender_name: 发送者昵称

        Returns:
            转发节点字典
        """
        pass

    def validate_message(self, message: dict[str, Any]) -> bool:
        """验证消息格式"""
        # 允许有文本内容 或者 有图片内容
        message_text = str(message.get("message_text", "")).strip()
        image_url = message.get("image_url", "") or message.get("poster_url", "")
        
        if not message_text and not image_url:
            self.logger.warning("消息缺少内容(无文本且无图片)")
            return False

        return True

    def get_platform_name(self) -> str:
        """获取平台名称"""
        return self.platform_name

    def log_send_attempt(self, message_count: int, method: str = "forward"):
        """记录发送尝试"""
        self.logger.info(
            f"[{self.platform_name}] 尝试{method}发送 {message_count} 条消息"
        )

    def log_send_result(
        self, success: bool, message_id: str | None = None, error: str | None = None
    ):
        """记录发送结果"""
        if success:
            self.logger.info(
                f"[{self.platform_name}] ✅ 发送成功，消息ID: {message_id or 'N/A'}"
            )
        else:
            self.logger.error(
                f"[{self.platform_name}] ❌ 发送失败: {error or 'Unknown error'}"
            )


class AdapterType:
    """适配器类型常量"""

    NAPCAT = "napcat"
    LLONEBOT = "llonebot"
    ONEBOT = "onebot"
    AIOCQHTTP = "aiocqhttp"
