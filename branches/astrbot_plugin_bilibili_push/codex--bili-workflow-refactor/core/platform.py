"""平台基类"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from .http import HttpClient
from .types import Category, Post, RawPost, SubUnit, Tag, Target


class Platform(ABC):
    """所有平台的基类"""

    platform_name: ClassVar[str]
    name: ClassVar[str]
    categories: ClassVar[dict[Category, str]] = {}
    enabled: ClassVar[bool] = True

    def __init__(self):
        # 移除了 ProcessContext，直接使用 HttpClient
        pass

    @classmethod
    async def get_client(cls):
        return await HttpClient.get_client()

    @abstractmethod
    async def get_target_name(self, target: Target) -> str | None:
        """获取订阅目标名称（如UP主名字）"""
        pass

    @abstractmethod
    async def fetch_new_post(self, sub_unit: SubUnit) -> list[Post]:
        """获取新消息（由子类实现具体策略）"""
        pass

    @abstractmethod
    def get_tags(self, raw_post: RawPost) -> list[Tag]:
        """获取标签"""
        pass

    @abstractmethod
    def get_category(self, raw_post: RawPost) -> Category:
        """获取分类"""
        pass

    @abstractmethod
    async def parse(self, raw_post: RawPost) -> Post:
        """解析原始消息为 Post"""
        pass


class NewMessagePlatform(Platform):
    """基于新消息列表的平台 (如 Bilibili 动态)"""

    @abstractmethod
    async def get_sub_list(self, target: Target) -> list[RawPost]:
        """获取目标的消息列表"""
        pass

    @abstractmethod
    def get_id(self, post: RawPost) -> Any:
        """获取消息唯一ID"""
        pass

    @abstractmethod
    def get_date(self, post: RawPost) -> int:
        """获取消息时间戳"""
        pass


class StatusChangePlatform(Platform):
    """基于状态变更的平台 (如 Bilibili 直播)"""

    @abstractmethod
    async def get_status(self, target: Target) -> Any:
        """获取当前状态"""
        pass

    @abstractmethod
    def compare_status(
        self, target: Target, old_status: Any, new_status: Any
    ) -> list[RawPost]:
        """比较状态生成消息"""
        pass
