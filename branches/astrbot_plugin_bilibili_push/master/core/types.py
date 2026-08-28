"""核心类型定义"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Optional, Union

Target = str
RawPost = Any
Category = int
Tag = str


class UserSubInfo(NamedTuple):
    user_id: str
    categories: list[Category]
    tags: list[Tag]


class SubUnit(NamedTuple):
    sub_target: Target
    user_sub_infos: list[UserSubInfo]


@dataclass
class Post:
    """标准推送消息结构"""

    platform: str
    content: str
    title: str
    timestamp: int
    url: str
    nickname: str
    images: list[str | bytes]
    id: str
    avatar: str | None = None
    repost: Optional["Post"] = None
    category: Optional[int] = None
    type: Any = None

    async def get_content(self) -> str:
        return self.content


class ApiError(Exception):
    def __init__(self, url: str):
        self.url = url
        super().__init__(f"API Error: {url}")


@dataclass
class MsgText:
    text: str


@dataclass
class MsgImage:
    data: str | Path | bytes


MessageSegment = Union[MsgText, MsgImage]
