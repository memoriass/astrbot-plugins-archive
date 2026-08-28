import re
from typing import Optional, Dict, Any
from ..core.http import HttpClient
from ..core.network_retry import get_with_retry
from ..utils.logger import logger
from ..utils.timezone import format_bilibili_time


class BilibiliParser:
    BV_PATTERN = re.compile(r"(BV[0-9a-zA-Z]{10})")
    AV_PATTERN = re.compile(r"av(\d+)")
    DYNAMIC_PATTERN = re.compile(r"(?:t\.bilibili\.com|bilibili\.com/dynamic)/(\d+)")
    OPUS_PATTERN = re.compile(r"bilibili\.com/opus/(\d+)")
    LIVE_PATTERN = re.compile(r"live\.bilibili\.com/(\d+)")
    SHORT_LINK_PATTERN = re.compile(r"(b23\.tv/[A-Za-z\d]+)")

    def __init__(self, display_timezone: str = "Asia/Shanghai"):
        self.display_timezone = display_timezone

    async def parse_message(self, text: str) -> Optional[Dict[str, Any]]:
        if m := self.SHORT_LINK_PATTERN.search(text):
            url = f"https://{m.group(1)}"
            try:
                client = await HttpClient.get_client()
                res = await client.head(url, follow_redirects=True, timeout=5.0)
                text = str(res.url)
            except Exception as e:
                logger.debug(f"Follow short link failed: {e}")

        if m := self.BV_PATTERN.search(text):
            return await self.get_video_info(bvid=m.group(1))
        if m := self.AV_PATTERN.search(text):
            return await self.get_video_info(avid=m.group(1))
        if m := self.DYNAMIC_PATTERN.search(text) or self.OPUS_PATTERN.search(text):
            return await self.get_dynamic_info(m.group(1))
        if m := self.LIVE_PATTERN.search(text):
            return await self.get_live_info(m.group(1))
        return None

    async def get_video_info(
        self, bvid: str = None, avid: str = None
    ) -> Optional[Dict[str, Any]]:
        client = await HttpClient.get_client()
        params = {"bvid": bvid} if bvid else {"aid": avid}
        try:
            res = await get_with_retry(
                client,
                "https://api.bilibili.com/x/web-interface/view",
                label=f"解析视频 {bvid or avid}",
                params=params,
            )
            data = res.json()
            if data.get("code") == 0 and (v := data.get("data")):
                return {
                    "type": "video",
                    "bvid": v.get("bvid") or bvid or "",
                    "aid": v.get("aid") or avid or "",
                    "cid": v.get("cid")
                    or (v.get("pages") or [{}])[0].get("cid", ""),
                    "title": v.get("title", ""),
                    "description": v.get("desc", ""),
                    "cover": v.get("pic", ""),
                    "duration": self._format_duration(v.get("duration", 0)),
                    "nickname": v.get("owner", {}).get("name", ""),
                    "avatar": v.get("owner", {}).get("face", ""),
                    "pub_time": format_bilibili_time(
                        v.get("pubdate", 0),
                        timezone_name=self.display_timezone,
                    ),
                    "stat": {
                        "view": v.get("stat", {}).get("view", 0),
                        "danmaku": v.get("stat", {}).get("danmaku", 0),
                    },
                }
        except Exception as e:
            logger.error(f"解析视频链接失败: {e}")
        return None

    async def get_dynamic_info(self, dynamic_id: str) -> Optional[Dict[str, Any]]:
        client = await HttpClient.get_client()
        try:
            res = await get_with_retry(
                client,
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
                label=f"解析动态 {dynamic_id}",
                params={"id": dynamic_id, "features": "itemOpusStyle"},
            )
            data = res.json()
            if data.get("code") == 0 and (item := data.get("data", {}).get("item")):
                modules = item.get("modules", {})
                module_author = modules.get("module_author", {})
                module_dynamic = modules.get("module_dynamic", {})
                major = module_dynamic.get("major") or {}
                desc = module_dynamic.get("desc") or {}
                return {
                    "type": "dynamic",
                    "title": self._dynamic_title(major),
                    "description": desc.get("text", "") or self._dynamic_description(major),
                    "cover": self._dynamic_cover(major),
                    "nickname": module_author.get("name", ""),
                    "avatar": module_author.get("face", ""),
                    "pub_time": format_bilibili_time(
                        module_author.get("pub_ts", 0),
                        timezone_name=self.display_timezone,
                    ),
                }
        except Exception as e:
            logger.error(f"解析动态链接失败: {e}")
        return None

    async def get_live_info(self, room_id: str) -> Optional[Dict[str, Any]]:
        client = await HttpClient.get_client()
        try:
            res = await get_with_retry(
                client,
                "https://api.live.bilibili.com/room/v1/Room/get_info",
                label=f"解析直播间 {room_id}",
                params={"id": room_id},
            )
            data = res.json()
            if data.get("code") == 0 and (r := data.get("data")):
                uid = r.get("uid")
                nickname, avatar = "未知主播", ""
                if uid:
                    res_u = await get_with_retry(
                        client,
                        "https://api.live.bilibili.com/live_user/v1/Master/info",
                        label=f"解析直播间主播 {uid}",
                        params={"uid": uid},
                    )
                    u_info = res_u.json().get("data", {}).get("info")
                    if u_info:
                        nickname, avatar = (
                            u_info.get("uname", nickname),
                            u_info.get("face", avatar),
                        )
                return {
                    "type": "live",
                    "title": r.get("title", ""),
                    "description": f"直播间ID: {room_id}",
                    "cover": r.get("user_cover") or r.get("cover") or "",
                    "nickname": nickname,
                    "avatar": avatar,
                    "pub_time": "正在直播" if r.get("live_status") == 1 else "未开播",
                }
        except Exception as e:
            logger.error(f"解析直播链接失败: {e}")
        return None

    async def get_user_info(self, uid: str) -> Optional[Dict[str, Any]]:
        client = await HttpClient.get_client()
        try:
            res = await get_with_retry(
                client,
                "https://api.bilibili.com/x/web-interface/card",
                label=f"获取用户信息 {uid}",
                params={"mid": uid},
                timeout=5,
            )
            data = res.json()
            if data["code"] == 0:
                card = data["data"]["card"]
                return {"username": card["name"], "face": card["face"], "uid": uid}
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
        return None

    def _dynamic_title(self, major: dict) -> str:
        if not isinstance(major, dict):
            return "B站动态"
        for key in ("archive", "article", "live", "opus"):
            title = (major.get(key) or {}).get("title")
            if title:
                return title
        return "B站动态"

    def _dynamic_description(self, major: dict) -> str:
        if not isinstance(major, dict):
            return ""
        article = major.get("article") or {}
        if article.get("desc"):
            return article["desc"]
        opus = major.get("opus") or {}
        summary = opus.get("summary") or {}
        return summary.get("text", "")

    def _dynamic_cover(self, major: dict) -> str:
        if not isinstance(major, dict):
            return ""
        draw_items = (major.get("draw") or {}).get("items") or []
        if draw_items:
            return draw_items[0].get("src", "")
        opus_pics = (major.get("opus") or {}).get("pics") or []
        if opus_pics:
            return opus_pics[0].get("url", "")
        archive = major.get("archive") or {}
        if archive.get("cover"):
            return archive["cover"]
        article_covers = (major.get("article") or {}).get("covers") or []
        if article_covers:
            return article_covers[0]
        live = major.get("live") or {}
        return live.get("cover", "")

    def _format_duration(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
