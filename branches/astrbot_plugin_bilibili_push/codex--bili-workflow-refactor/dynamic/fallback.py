import json

from ..core.models import ArticleMajor, DrawMajor, DynRawPost, PostAPI, VideoMajor
from ..utils.logger import logger


def _get_any(data: dict, *keys):
    for key in keys:
        if "." in key:
            value = data
            try:
                for part in key.split("."):
                    if not isinstance(value, dict):
                        value = None
                        break
                    value = value.get(part)
            except Exception:
                value = None
            if value:
                return value
        elif data.get(key):
            return data[key]
    return ""


class FallbackCardConverter:
    def _convert_fallback_card(self, desc: dict, card_json: dict) -> DynRawPost | None:
        try:
            type_map = {
                8: "DYNAMIC_TYPE_AV",
                2: "DYNAMIC_TYPE_DRAW",
                11: "DYNAMIC_TYPE_DRAW",
                64: "DYNAMIC_TYPE_ARTICLE",
                12: "DYNAMIC_TYPE_ARTICLE",
                1: "DYNAMIC_TYPE_FORWARD",
                4: "DYNAMIC_TYPE_WORD",
            }

            try:
                raw_type = int(desc.get("type", 0))
            except Exception:
                raw_type = 0

            if raw_type == 0:
                if "aid" in card_json:
                    raw_type = 8
                elif "item" in card_json and "pictures" in card_json["item"]:
                    raw_type = 2
                elif "item" in card_json and "upload_time" in card_json["item"]:
                    raw_type = 4

            dyn_type = type_map.get(raw_type, "DYNAMIC_TYPE_WORD")
            user_profile = desc.get("user_profile", {}).get("info", {})
            if not user_profile:
                user_profile = card_json.get("user", {})

            author = PostAPI.Modules.Author(
                face=user_profile.get("face", "") or user_profile.get("head_url", ""),
                mid=user_profile.get("uid", 0),
                name=user_profile.get("uname", "") or user_profile.get("name", ""),
                jump_url=f"https://space.bilibili.com/{user_profile.get('uid', 0)}",
                pub_ts=desc.get("timestamp", 0)
                or _get_any(card_json, "item.upload_time", "pubdate", "ctime")
                or 0,
                type="AUTHOR_TYPE_NORMAL",
            )

            major = None
            text_desc = ""
            orig_item = None

            if dyn_type == "DYNAMIC_TYPE_AV":
                bvid = desc.get("bvid", "") or card_json.get("bvid", "")
                major = VideoMajor(
                    type="MAJOR_TYPE_ARCHIVE",
                    archive=VideoMajor.Archive(
                        aid=str(card_json.get("aid", "")),
                        bvid=bvid,
                        title=card_json.get("title", ""),
                        desc=card_json.get("desc", ""),
                        cover=card_json.get("pic", ""),
                        jump_url=f"https://www.bilibili.com/video/{bvid}",
                    ),
                )
                text_desc = card_json.get("dynamic", "")

            elif dyn_type == "DYNAMIC_TYPE_DRAW":
                items = [
                    DrawMajor.Item(width=0, height=0, src=pic.get("img_src", ""))
                    for pic in (
                        _get_any(card_json, "item.pictures", "item.images", "pics")
                        or []
                    )
                ]
                major = DrawMajor(
                    type="MAJOR_TYPE_DRAW",
                    draw=DrawMajor.Draw(
                        id=0,
                        items=items,
                        title=_get_any(card_json, "item.title", "title"),
                    ),
                )
                text_desc = _get_any(
                    card_json, "item.description", "item.content", "desc"
                )

            elif dyn_type == "DYNAMIC_TYPE_WORD":
                text_desc = _get_any(
                    card_json, "item.content", "item.description", "dynamic"
                )
                pics = _get_any(card_json, "item.pictures", "item.images", "pics") or []
                items = [
                    DrawMajor.Item(width=0, height=0, src=pic.get("img_src", ""))
                    for pic in pics
                ]
                if items:
                    dyn_type = "DYNAMIC_TYPE_DRAW"
                    major = DrawMajor(
                        type="MAJOR_TYPE_DRAW",
                        draw=DrawMajor.Draw(id=0, items=items),
                    )

            elif dyn_type == "DYNAMIC_TYPE_ARTICLE":
                major = ArticleMajor(
                    type="MAJOR_TYPE_ARTICLE",
                    article=ArticleMajor.Article(
                        id=desc.get("rid", 0),
                        title=card_json.get("title", ""),
                        desc=card_json.get("summary", ""),
                        covers=card_json.get("image_urls", []),
                        jump_url=f"https://www.bilibili.com/read/cv{desc.get('rid', '')}",
                    ),
                )

            elif dyn_type == "DYNAMIC_TYPE_FORWARD":
                text_desc = _get_any(card_json, "item.content", "dynamic", "desc")
                orig_item = self._convert_origin_card(card_json)

            if not text_desc:
                text_desc = _get_any(
                    card_json, "dynamic", "desc", "summary", "title", "content"
                )

            return PostAPI.Item(
                basic=PostAPI.Basic(rid_str=str(desc.get("rid", ""))),
                id_str=str(desc.get("dynamic_id_str", "")),
                type=dyn_type,
                orig=orig_item,
                modules=PostAPI.Modules(
                    module_author=author,
                    module_dynamic=PostAPI.Modules.Dynamic(
                        major=major,
                        desc=PostAPI.Modules.Desc(text=text_desc, rich_text_nodes=[]),
                    ),
                ),
            )
        except Exception as exc:
            logger.warning(
                f"Convert logic error ({exc}) for card: {str(card_json)[:100]}..."
            )
            return None

    def _convert_origin_card(self, card_json: dict) -> DynRawPost | None:
        if "origin" not in card_json:
            return None
        try:
            origin_json = json.loads(card_json["origin"])
            orig_type = card_json.get("item", {}).get("orig_type")
            if not orig_type:
                if "aid" in origin_json:
                    orig_type = 8
                elif "item" in origin_json and "pictures" in origin_json["item"]:
                    orig_type = 2

            orig_desc = {
                "type": orig_type,
                "user_profile": {"info": origin_json.get("user", {})},
                "timestamp": _get_any(
                    origin_json, "item.upload_time", "pubdate", "ctime"
                )
                or 0,
                "rid": origin_json.get("rid", ""),
                "bvid": origin_json.get("bvid", ""),
            }
            return self._convert_fallback_card(orig_desc, origin_json)
        except Exception as exc:
            logger.warning(f"Failed to parse forwarded content: {exc}")
            return None
