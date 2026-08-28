"""
NapCat 协议适配器
基于 NapCat 文档实现的合并转发消息发送适配器
支持 send_forward_msg API
"""

from typing import Any

from .adapter_base import BaseAdapter


class NapCatAdapter(BaseAdapter):
    """NapCat 协议适配器"""

    def __init__(self, platform_name: str):
        super().__init__(platform_name)

    async def send_forward_messages(
        self, bot_client: Any, group_id: str, messages: list[dict[str, Any]], **kwargs
    ) -> dict[str, Any]:
        """
        使用 NapCat 的 send_forward_msg API 发送合并转发消息

        Args:
            bot_client: NapCat 客户端实例
            group_id: 群组ID
            messages: 消息列表
            **kwargs: 其他参数，支持 user_id (私聊), sender_id, sender_name

        Returns:
            发送结果
        """
        try:
            self.log_send_attempt(len(messages), "NapCat合并转发")

            # 验证消息
            valid_messages = [msg for msg in messages if self.validate_message(msg)]
            if not valid_messages:
                return {"success": False, "error": "没有有效的消息"}

            # 构建转发节点
            sender_id = kwargs.get("sender_id", "2659908767")
            sender_name = kwargs.get("sender_name", "媒体通知")

            forward_nodes = []
            for msg in valid_messages:
                node = self.build_forward_node(msg, sender_id, sender_name)
                forward_nodes.append(node)

            # 构建 NapCat 格式的请求参数
            if kwargs.get("user_id"):
                # 私聊合并转发
                payload = {"user_id": int(kwargs["user_id"]), "messages": forward_nodes}
                result = await bot_client.call_action(
                    "send_private_forward_msg", **payload
                )
            else:
                # 群聊合并转发
                payload = {"group_id": int(group_id), "messages": forward_nodes}
                result = await bot_client.call_action(
                    "send_group_forward_msg", **payload
                )

            # 处理返回结果
            message_id = result.get("message_id") if result else None
            self.log_send_result(True, str(message_id) if message_id else None)

            return {"success": True, "message_id": message_id, "result": result}

        except Exception as e:
            error_msg = f"NapCat 发送失败: {str(e)}"
            self.log_send_result(False, error=error_msg)
            return {"success": False, "error": error_msg}

    def build_forward_node(
        self,
        message: dict[str, Any],
        sender_id: str = "2659908767",
        sender_name: str = "媒体通知",
    ) -> dict[str, Any]:
        """
        构建 NapCat 格式的转发节点

        根据 go-cqhttp 标准格式：
        - 使用 name 和 uin 字段
        - uin 为字符串类型
        - content 为消息段数组

        Args:
            message: 消息内容
            sender_id: 发送者QQ号
            sender_name: 发送者昵称

        Returns:
            NapCat 格式的转发节点
        """
        # 构建消息内容
        content = []

        # 添加图片（如果有）
        # 添加图片（如果有）
        if message.get("image_url"):
            # 添加 summary 参数触发 NapCat 的压缩逻辑，防止图片过大发送失败
            content.append(
                {
                    "type": "image",
                    "data": {"file": message["image_url"], "summary": "AstrBot_Compressed"},
                }
            )

        # 添加文本
        message_text = str(message.get("message_text", "")).strip()
        if message_text:
            content.append({"type": "text", "data": {"text": message_text}})

        # 如果没有任何内容，添加默认文本
        if not content:
            content.append({"type": "text", "data": {"text": "[媒体通知]"}})

        # 构建 NapCat 转发节点格式（go-cqhttp 标准）
        # 参考：https://docs.go-cqhttp.org/cqcode/#合并转发消息节点
        return {
            "type": "node",
            "data": {
                "name": sender_name,
                "uin": str(sender_id),  # go-cqhttp 标准使用字符串
                "content": content,
            },
        }

    def get_adapter_info(self) -> dict[str, Any]:
        """获取适配器信息"""
        return {
            "name": "NapCat",
            "version": "1.0.0",
            "description": "基于 NapCat 文档的合并转发适配器",
            "supported_apis": ["send_group_forward_msg", "send_private_forward_msg"],
            "features": [
                "群聊合并转发",
                "私聊合并转发",
                "图片消息支持",
                "自定义发送者信息",
            ],
        }
