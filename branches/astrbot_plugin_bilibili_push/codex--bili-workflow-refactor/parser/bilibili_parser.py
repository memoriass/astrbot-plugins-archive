import re
import time
from typing import Optional, Dict, Any
from ..core.http import HttpClient
from ..utils.logger import logger


class BilibiliParser:
    BV_PATTERN = re.compile(r"(BV[0-9a-zA-Z]{10})")
    AV_PATTERN = re.compile(r"av(\d+)")
    DYNAMIC_PATTERN = re.compile(r"(?:t\.bilibili\.com|bilibili\.com/dynamic)/(\d+)")
    OPUS_PATTERN = re.compile(r"bilibili\.com/opus/(\d+)")
    LIVE_PATTERN = re.compile(r"live\.bilibili\.com/(\d+)")
    SHORT_LINK_PATTERN = re.compile(r"(b23\.tv/[A-Za-z\d]+)")

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
            res = await client.get(
                "https://api.bilibili.com/x/web-interface/view", params=params
            )
            data = res.json()
            if data.get("code") == 0 and (v := data.get("data")):
                return {
                    "type": "video",
                    "title": v.get("title", ""),
                    "description": v.get("desc", ""),
                    "cover": v.get("pic", ""),
                    "duration": self._format_duration(v.get("duration", 0)),
                    "nickname": v.get("owner", {}).get("name", ""),
                    "avatar": v.get("owner", {}).get("face", ""),
                    "pub_time": v.get("pubdate", 0),
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
            res = await client.get(
                "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
                params={"id": dynamic_id, "features": "itemOpusStyle"},
            )
            data = res.json()
            if data.get("code") == 0 and (item := data.get("data", {}).get("item")):
                modules = item.get("modules", {})
                module_author = modules.get("module_author", {})
                module_dynamic = modules.get("module_dynamic", {})
                return {
                    "type": "dynamic",
                    "title": "B站动态",
                    "description": module_dynamic.get("desc", {}).get("text", ""),
                    "cover": module_dynamic.get("major", {})
                    .get("draw", {})
                    .get("items", [{}])[0]
                    .get("src", ""),
                    "nickname": module_author.get("name", ""),
                    "avatar": module_author.get("face", ""),
                    "pub_time": module_author.get("pub_ts", 0),
                }
        except Exception as e:
            logger.error(f"解析动态链接失败: {e}")
        return None

    async def get_live_info(self, room_id: str) -> Optional[Dict[str, Any]]:
        client = await HttpClient.get_client()
        try:
            res = await client.get(
                "https://api.live.bilibili.com/room/v1/Room/get_info",
                params={"id": room_id},
            )
            data = res.json()
            if data.get("code") == 0 and (r := data.get("data")):
                uid = r.get("uid")
                nickname, avatar = "未知主播", ""
                if uid:
                    res_u = await client.get(
                        "https://api.live.bilibili.com/live_user/v1/Master/info",
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
            res = await client.get(
                "https://api.bilibili.com/x/web-interface/card",
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

    def _format_duration(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
