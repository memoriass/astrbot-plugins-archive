from __future__ import annotations

from dataclasses import asdict, dataclass
import re

_MECHANICAL = (
    "我将调用",
    "请稍候",
    "执行部门返回",
    "启动外部网络检索协议",
    "系统反馈异常",
    "请问现在需要我这么做吗",
    "随时在此待命",
    "已彻底挂起",
)
_FORMAL = re.compile(r"(?:为您|请您|您可以|请问您|务必)")
_REPEATED_ADDRESS = re.compile(r"(?:^|[。！？\n])\s*(零|主人|管理员)[，,:：]?")


@dataclass(frozen=True, slots=True)
class ResponseStyleReview:
    mechanical_markers: tuple[str, ...]
    formal_count: int
    address_count: int
    asks_unnecessary_follow_up: bool

    @property
    def natural(self) -> bool:
        return not self.mechanical_markers and self.formal_count <= 1 and self.address_count <= 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def review_response_style(text: str) -> ResponseStyleReview:
    clean = str(text or "")
    mechanical = tuple(marker for marker in _MECHANICAL if marker in clean)
    follow_up = bool(re.search(r"(?:请问|需要我|要不要我).{0,24}(?:吗|？|\?)\s*$", clean))
    return ResponseStyleReview(
        mechanical_markers=mechanical,
        formal_count=len(_FORMAL.findall(clean)),
        address_count=len(_REPEATED_ADDRESS.findall(clean)),
        asks_unnecessary_follow_up=follow_up,
    )
