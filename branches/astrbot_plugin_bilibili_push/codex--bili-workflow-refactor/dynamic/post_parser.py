from typing import NamedTuple

from yarl import URL

from ..core.compat import type_validate_json
from ..core.models import (
    ArticleMajor,
    DrawMajor,
    DynamicType,
    DynRawPost,
    LiveMajor,
    LiveRecommendMajor,
    OPUSMajor,
    PostAPI,
    VideoMajor,
)
from ..core.types import Category, Post, Tag
from ..core.utils import text_similarity


class _ProcessedText(NamedTuple):
    title: str
    content: str


class _ParsedMajorPost(NamedTuple):
    title: str
    content: str
    pics: list[str]
    url: str | None = None


class DynamicPostParser:
    def get_id(self, post: DynRawPost) -> str:
        return post.id_str or str(post.basic.rid_str)

    def get_date(self, post: DynRawPost) -> int:
        return post.modules.module_author.pub_ts

    def _do_get_category(self, post_type: DynamicType) -> Category:
        match post_type:
            case (
                "DYNAMIC_TYPE_DRAW"
                | "DYNAMIC_TYPE_COMMON_VERTICAL"
                | "DYNAMIC_TYPE_COMMON_SQUARE"
            ):
                return Category(1)
            case "DYNAMIC_TYPE_ARTICLE":
                return Category(2)
            case "DYNAMIC_TYPE_AV":
                return Category(3)
            case "DYNAMIC_TYPE_WORD":
                return Category(4)
            case "DYNAMIC_TYPE_FORWARD":
                return Category(5)
            case "DYNAMIC_TYPE_LIVE_RCMD" | "DYNAMIC_TYPE_LIVE":
                return Category(6)
            case _:
                return Category(99)

    def get_category(self, post: DynRawPost) -> Category:
        return self._do_get_category(post.type)

    def get_tags(self, raw_post: DynRawPost) -> list[Tag]:
        tags: list[Tag] = []
        if raw_post.topic:
            tags.append(raw_post.topic.name)
        if desc := raw_post.modules.module_dynamic.desc:
            for node in desc.rich_text_nodes:
                if node.get("type") == "RICH_TEXT_NODE_TYPE_TOPIC":
                    tags.append(node["text"].strip("#"))
        return tags

    def _text_process(self, dynamic: str, desc: str, title: str) -> _ProcessedText:
        title_similarity = (
            0.0
            if len(title) == 0 or len(desc) == 0
            else text_similarity(title, desc[: len(title)])
        )
        if title_similarity > 0.9:
            desc = desc[len(title) :].lstrip()
        content_similarity = (
            0.0
            if len(dynamic) == 0 or len(desc) == 0
            else text_similarity(dynamic, desc)
        )
        if content_similarity > 0.8:
            return _ProcessedText(title, desc if len(dynamic) < len(desc) else dynamic)
        return _ProcessedText(
            title,
            f"{desc}" + (f"\n=================\n{dynamic}" if dynamic else ""),
        )

    def pre_parse_by_mojar(self, raw_post: DynRawPost) -> _ParsedMajorPost:
        dyn = raw_post.modules.module_dynamic
        major = dyn.major

        if isinstance(major, VideoMajor):
            archive = major.archive
            desc_text = dyn.desc.text if dyn.desc else ""
            parsed = self._text_process(desc_text, archive.desc, archive.title)
            return _ParsedMajorPost(
                parsed.title,
                parsed.content,
                [archive.cover],
                str(URL(archive.jump_url).with_scheme("https")),
            )
        if isinstance(major, LiveRecommendMajor):
            live_rcmd = major.live_rcmd
            content_data = type_validate_json(
                LiveRecommendMajor.Content, live_rcmd.content
            )
            live_info = content_data.live_play_info
            return _ParsedMajorPost(
                live_info.title,
                f"{live_info.parent_area_name} {live_info.area_name}",
                [live_info.cover],
                str(URL(live_info.link).with_scheme("https").with_query(None)),
            )
        if isinstance(major, LiveMajor):
            live = major.live
            return _ParsedMajorPost(
                live.title,
                f"{live.desc_first}\n{live.desc_second}",
                [live.cover],
                str(URL(live.jump_url).with_scheme("https")),
            )
        if isinstance(major, DrawMajor):
            return self._parse_draw(raw_post, major)
        if isinstance(major, ArticleMajor):
            return _ParsedMajorPost(
                major.article.title,
                major.article.desc,
                major.article.covers,
                str(URL(major.article.jump_url).with_scheme("https")),
            )
        if isinstance(major, OPUSMajor):
            opus = major.opus
            text = opus.summary.text
            title = opus.title or self._title_from_text(text)
            return _ParsedMajorPost(
                title,
                text,
                [pic.url for pic in opus.pics],
                opus.jump_url,
            )

        desc = dyn.desc.text if dyn.desc else ""
        return _ParsedMajorPost("", desc, [], f"https://t.bilibili.com/{raw_post.id_str}")

    def _parse_draw(self, raw_post: DynRawPost, major: DrawMajor) -> _ParsedMajorPost:
        dyn = raw_post.modules.module_dynamic
        text = dyn.desc.text if dyn.desc else ""
        if not text:
            item_descs = [item.description for item in major.draw.items if item.description]
            if item_descs:
                text = "\n".join(item_descs)
        title = major.draw.title or self._title_from_text(text)
        return _ParsedMajorPost(
            title,
            text,
            [item.src for item in major.draw.items],
            f"https://t.bilibili.com/{raw_post.id_str}",
        )

    def _title_from_text(self, text: str) -> str:
        if not text:
            return ""
        first_line = text.split("\n")[0]
        return first_line[:30] + "..." if len(first_line) > 30 else first_line

    async def parse(self, raw_post: DynRawPost) -> Post:
        parsed_raw_post = self.pre_parse_by_mojar(raw_post)
        repost = self._parse_repost(raw_post)

        return Post(
            platform=self.platform_name,
            content=parsed_raw_post.content,
            title=parsed_raw_post.title,
            images=list(parsed_raw_post.pics),
            timestamp=self.get_date(raw_post),
            url=parsed_raw_post.url or "",
            nickname=raw_post.modules.module_author.name,
            avatar=raw_post.modules.module_author.face,
            id=self.get_id(raw_post),
            repost=repost,
            type=raw_post.type,
            category=self.get_category(raw_post),
        )

    def _parse_repost(self, raw_post: DynRawPost) -> Post | None:
        if self.get_category(raw_post) != Category(5) or not raw_post.orig:
            return None
        if not isinstance(raw_post.orig, PostAPI.Item):
            return None

        parsed_repost = self.pre_parse_by_mojar(raw_post.orig)
        return Post(
            platform=self.platform_name,
            content=parsed_repost.content,
            title=parsed_repost.title,
            images=list(parsed_repost.pics),
            timestamp=self.get_date(raw_post.orig),
            url=parsed_repost.url or "",
            nickname=raw_post.orig.modules.module_author.name,
            avatar=raw_post.orig.modules.module_author.face,
            id=self.get_id(raw_post.orig),
        )
