import asyncio
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import logger

from ..core.http import HttpClient
from ..rendering import RendererPort


class SubscriptionListPresenter:
    def __init__(self, db, bg_dir: Path, renderer: RendererPort):
        self.db = db
        self.bg_folder = bg_dir
        self.renderer = renderer

    async def show(self, event, target_id: str, scheduler):
        subs = self.db.get_subscriptions(target_id)
        if not subs:
            yield event.plain_result("📭 当前会话无订阅")
            return

        yield event.plain_result("⏳ 正在获取订阅详细信息...")
        subs_map = self._build_sub_map(subs)
        face_map = await self._fetch_face_map(subs_map.keys())
        live_status_map = await self._fetch_live_status_map(subs_map, scheduler)
        all_subs = self._compose_rows(subs_map, face_map, live_status_map)

        try:
            img_bytes = await self.renderer.render(
                "sub_list.html.jinja",
                {
                    "subs": all_subs,
                    "page_title": "订阅列表",
                },
                viewport={"width": 1000, "height": 800},
                selector=".card-board",
            )
            yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
        except Exception as exc:
            logger.error(f"Render list failed: {exc}")
            yield event.plain_result("❌ 列表渲染失败")

    def _build_sub_map(self, subs) -> dict:
        subs_map = {}
        for sub in subs:
            if sub.uid not in subs_map:
                subs_map[sub.uid] = {
                    "uid": sub.uid,
                    "username": sub.username,
                    "has_dynamic": False,
                    "has_live": False,
                }
            if sub.sub_type == "dynamic":
                subs_map[sub.uid]["has_dynamic"] = True
            elif sub.sub_type == "live":
                subs_map[sub.uid]["has_live"] = True
        return subs_map

    async def _fetch_face_map(self, uids) -> dict:
        client = await HttpClient.get_client()

        async def fetch_info(uid):
            face = "http://i0.hdslb.com/bfs/face/member/noface.jpg"
            try:
                res = await client.get(
                    "https://api.bilibili.com/x/web-interface/card",
                    params={"mid": uid},
                    timeout=5,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data["code"] == 0:
                        face = data["data"]["card"]["face"]
            except Exception:
                pass
            return uid, face

        info_results = await asyncio.gather(*[fetch_info(uid) for uid in uids])
        return dict(info_results)

    async def _fetch_live_status_map(self, subs_map: dict, scheduler) -> dict:
        live_uids = [uid for uid, sub in subs_map.items() if sub["has_live"]]
        if not live_uids:
            return {}
        try:
            live_infos = await scheduler.live_platform.batch_get_status(live_uids)
            return {str(info.uid): info.live_status == 1 for info in live_infos}
        except Exception:
            return {}

    def _compose_rows(self, subs_map: dict, face_map: dict, live_status_map: dict):
        all_subs = []
        for uid, info in subs_map.items():
            info["face"] = face_map.get(str(uid), "")
            info["is_live"] = live_status_map.get(str(uid), False)
            all_subs.append(info)
        return all_subs
