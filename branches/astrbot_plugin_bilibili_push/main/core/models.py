from typing import Any, Literal, TypeAlias, TypeVar

from pydantic import BaseModel

from .compat import PYDANTIC_V2, ConfigDict, model_rebuild

TBaseModel = TypeVar("TBaseModel", bound=type[BaseModel])

def model_rebuild_recurse(cls: TBaseModel) -> TBaseModel:
    """重建嵌套 Pydantic 模型。"""
    from inspect import getmembers, isclass

    for _, sub_cls in getmembers(
        cls, lambda x: isclass(x) and issubclass(x, BaseModel)
    ):
        if sub_cls is cls:
            continue
        model_rebuild_recurse(sub_cls)

    model_rebuild(cls)
    return cls


class Base(BaseModel):
    if PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:

        class Config:
            orm_mode = True


class APIBase(Base):
    """Bilibili API返回的基础数据"""

    code: int
    message: str


class UserAPI(APIBase):
    class Info(Base):
        uname: str | None = None
        name: str | None = None
        face: str | None = None

    class Data(Base):
        info: "UserAPI.Info | None" = None
        card: "UserAPI.Info | None" = None

    data: Data | None = None


DynamicType = Literal[
    "DYNAMIC_TYPE_ARTICLE",
    "DYNAMIC_TYPE_AV",
    "DYNAMIC_TYPE_WORD",
    "DYNAMIC_TYPE_DRAW",
    "DYNAMIC_TYPE_FORWARD",
    "DYNAMIC_TYPE_LIVE",
    "DYNAMIC_TYPE_LIVE_RCMD",
    "DYNAMIC_TYPE_PGC",
    "DYNAMIC_TYPE_PGC_UNION",
    "DYNAMIC_TYPE_NONE",
    "DYNAMIC_TYPE_COMMON_SQUARE",
    "DYNAMIC_TYPE_COMMON_VERTICAL",
    "DYNAMIC_TYPE_COURSES_SEASON",
]

class PostAPI(APIBase):
    class Basic(Base):
        rid_str: str

    class Modules(Base):
        class Author(Base):
            face: str
            mid: int
            name: str
            jump_url: str
            pub_ts: int
            type: Literal["AUTHOR_TYPE_NORMAL", "AUTHOR_TYPE_PGC"]

        class Additional(Base):
            type: str

        class Desc(Base):
            rich_text_nodes: list[dict[str, Any]]
            text: str

        class Dynamic(Base):
            additional: "PostAPI.Modules.Additional | None" = None
            desc: "PostAPI.Modules.Desc | None" = None
            major: "Major | None" = None

        module_author: "PostAPI.Modules.Author"
        module_dynamic: "PostAPI.Modules.Dynamic"

    class Topic(Base):
        id: int
        name: str
        jump_url: str

    class Item(Base):
        basic: "PostAPI.Basic"
        id_str: str
        modules: "PostAPI.Modules"
        orig: "PostAPI.Item | PostAPI.DeletedItem | None" = None
        topic: "PostAPI.Topic | None" = None
        type: DynamicType

    class DeletedItem(Base):
        basic: "PostAPI.Basic"
        id_str: None
        modules: "PostAPI.Modules"
        type: Literal["DYNAMIC_TYPE_NONE"]

        def to_item(self) -> "PostAPI.Item":
            return PostAPI.Item(
                basic=self.basic,
                id_str="",
                modules=self.modules,
                type=self.type,
            )

    class Data(Base):
        items: "list[PostAPI.Item | PostAPI.DeletedItem] | None" = None

    data: "PostAPI.Data | None" = None


class VideoMajor(Base):
    class Archive(Base):
        aid: str
        bvid: str
        title: str
        desc: str
        cover: str
        jump_url: str

    type: Literal["MAJOR_TYPE_ARCHIVE"]
    archive: "VideoMajor.Archive"


class LiveRecommendMajor(Base):
    class LiveRecommand(Base):
        content: str

    class Content(Base):
        type: int
        live_play_info: "LiveRecommendMajor.LivePlayInfo"

    class LivePlayInfo(Base):
        uid: int
        room_type: int
        room_paid_type: int
        play_type: int
        live_status: int
        live_screen_type: int
        room_id: int
        cover: str
        title: str
        online: int
        parent_area_id: int
        parent_area_name: str
        area_id: int
        area_name: str
        live_start_time: int
        link: str
        live_id: str | int
        watched_show: "LiveRecommendMajor.WatchedShow"

    class WatchedShow(Base):
        num: int
        text_small: str
        text_large: str
        switch: bool
        icon: str
        icon_web: str
        icon_location: str

    type: Literal["MAJOR_TYPE_LIVE_RCMD"]
    live_rcmd: "LiveRecommendMajor.LiveRecommand"


class LiveMajor(Base):
    class Live(Base):
        id: int
        title: str
        live_state: int
        cover: str
        desc_first: str
        desc_second: str
        jump_url: str

    type: Literal["MAJOR_TYPE_LIVE"]
    live: "LiveMajor.Live"


class ArticleMajor(Base):
    class Article(Base):
        id: int
        title: str
        desc: str
        covers: list[str]
        jump_url: str

    type: Literal["MAJOR_TYPE_ARTICLE"]
    article: "ArticleMajor.Article"


class DrawMajor(Base):
    class Item(Base):
        width: int
        height: int
        size: float | None = None
        src: str
        description: str | None = None

    class Draw(Base):
        id: int
        items: "list[DrawMajor.Item]"
        title: str | None = None

    type: Literal["MAJOR_TYPE_DRAW"]
    draw: "DrawMajor.Draw"


class PGCMajor(Base):
    """番剧推送"""

    class PGC(Base):
        title: str
        cover: str
        jump_url: str
        epid: int
        season_id: int

    type: Literal["MAJOR_TYPE_PGC"]
    pgc: "PGCMajor.PGC"


class OPUSMajor(Base):
    """通用图文内容"""

    class Summary(Base):
        rich_text_nodes: list[dict[str, Any]]
        text: str

    class Pic(Base):
        width: int
        height: int
        size: float | None = None
        url: str

    class Opus(Base):
        jump_url: str
        title: str | None
        summary: "OPUSMajor.Summary"
        pics: "list[OPUSMajor.Pic]"

    type: Literal["MAJOR_TYPE_OPUS"]
    opus: "OPUSMajor.Opus"


class CommonMajor(Base):
    """特殊官方功能卡片。"""

    class Common(Base):
        cover: str
        title: str
        desc: str
        jump_url: str

    type: Literal["MAJOR_TYPE_COMMON"]
    common: "CommonMajor.Common"


class CoursesMajor(Base):
    """课程推送"""

    class Courses(Base):
        title: str
        sub_title: str
        desc: str
        cover: str
        jump_url: str
        id: int

    type: Literal["MAJOR_TYPE_COURSES"]
    courses: "CoursesMajor.Courses"


class DeletedMajor(Base):
    class None_(Base):
        tips: str

    type: Literal["MAJOR_TYPE_NONE"]
    none: "DeletedMajor.None_"


class UnknownMajor(Base):
    type: str


Major = (
    VideoMajor
    | LiveRecommendMajor
    | LiveMajor
    | ArticleMajor
    | DrawMajor
    | PGCMajor
    | OPUSMajor
    | CommonMajor
    | CoursesMajor
    | DeletedMajor
    | UnknownMajor
)

DynRawPost: TypeAlias = PostAPI.Item

model_rebuild_recurse(VideoMajor)
model_rebuild_recurse(LiveRecommendMajor)
model_rebuild_recurse(LiveMajor)
model_rebuild_recurse(ArticleMajor)
model_rebuild_recurse(DrawMajor)
model_rebuild_recurse(PGCMajor)
model_rebuild_recurse(OPUSMajor)
model_rebuild_recurse(CommonMajor)
model_rebuild_recurse(CoursesMajor)
model_rebuild_recurse(UserAPI)
model_rebuild_recurse(PostAPI)
