from abc import ABC, abstractmethod
from ...core.types import MessageSegment, Post


class Theme(ABC):
    @abstractmethod
    async def render(self, post: Post) -> list[MessageSegment]:
        pass

    async def is_support_render(self, post: Post) -> bool:
        return True
