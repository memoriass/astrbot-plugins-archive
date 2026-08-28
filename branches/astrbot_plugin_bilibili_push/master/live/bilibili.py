"""Bilibili 直播平台实现"""

from copy import deepcopy
from enum import Enum, unique
from typing import ClassVar

from pydantic import BaseModel, Field

from ..core.compat import (
    PYDANTIC_V2,
    ConfigDict,
    type_validate_json,
    type_validate_python,
)
from ..core.network_retry import get_with_retry

from ..core.platform import StatusChangePlatform
from ..core.types import Category, Post, RawPost, Tag, Target
from ..utils.logger import logger

from ..core.models import UserAPI


class BilibiliLive(StatusChangePlatform):
    platform_name = "bilibili-live"
    name = "Bilibili直播"
    categories: ClassVar[dict[Category, str]] = {
        1: "开播提醒",
        2: "标题更新提醒",
        3: "下播提醒",
    }

    @unique
    class LiveStatus(Enum):
        OFF = 0
        ON = 1
        CYCLE = 2

    @unique
    class LiveAction(Enum):
        TURN_ON = "turn_on"
        TURN_OFF = "turn_off"
        ON = "on"
        OFF = "off"
        TITLE_UPDATE = "title_update"

    class Info(BaseModel):
        if PYDANTIC_V2:
            model_config = ConfigDict(populate_by_name=True)
        else:

            class Config:
                allow_population_by_field_name = True

        title: str
        room_id: int
        uid: int
        live_time: int
        live_status: int
        area_name: str = Field(alias="area_v2_name")
        uname: str
        face: str
        cover: str = Field(alias="cover_from_user")
        keyframe: str
        category: Category = Field(default=Category(0))

        def get_live_action(
            self, old_info: "BilibiliLive.Info"
        ) -> "BilibiliLive.LiveAction":
            if old_info.live_status in [0, 2] and self.live_status == 1:
                return BilibiliLive.LiveAction.TURN_ON
            elif old_info.live_status == 1 and self.live_status in [0, 2]:
                return BilibiliLive.LiveAction.TURN_OFF
            elif old_info.live_status == 1 and self.live_status == 1:
                if old_info.title != self.title:
                    return BilibiliLive.LiveAction.TITLE_UPDATE
                return BilibiliLive.LiveAction.ON
            else:
                return BilibiliLive.LiveAction.OFF

    async def get_target_name(self, target: Target) -> str | None:
        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.bilibili.com/x/web-interface/card",
            label=f"获取直播目标名称 {target}",
            params={"mid": target},
        )
        if res.status_code != 200:
            res = await get_with_retry(
                client,
                "https://api.live.bilibili.com/live_user/v1/Master/info",
                label=f"获取直播目标备用名称 {target}",
                params={"uid": target},
            )
            if res.status_code != 200:
                return None

        res_data = type_validate_json(UserAPI, res.content)
        if res_data.code != 0:
            return None

        if not res_data.data:
            return None

        if res_data.data.card:
            return res_data.data.card.name
        if res_data.data.info:
            return res_data.data.info.uname or res_data.data.info.name
        return None

    def _gen_empty_info(self, uid: int) -> Info:
        return BilibiliLive.Info(
            title="",
            room_id=0,
            uid=uid,
            live_time=0,
            live_status=0,
            area_v2_name="",
            uname="",
            face="",
            cover_from_user="",
            keyframe="",
        )

    async def get_status(self, target: Target) -> Info:
        infos = await self.batch_get_status([target])
        return infos[0]

    async def batch_get_status(self, targets: list[Target]) -> list[Info]:
        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            label=f"直播状态批量检查 {len(targets)} 个 UID",
            params={"uids[]": targets},
            timeout=10.0,
        )
        if res.status_code in {403, 412}:
            return await self._retry_batch_after_risk(targets, res.status_code)
        res_dict = res.json()
        if res_dict["code"] != 0:
            if str(res_dict["code"]) in {"-352", "352", "403", "412"}:
                return await self._retry_batch_after_risk(targets, int(res_dict["code"]))
            raise Exception("API Error")

        data = res_dict.get("data", {})
        infos = []
        for target in targets:
            if target in data.keys():
                infos.append(type_validate_python(self.Info, data[target]))
            else:
                infos.append(self._gen_empty_info(int(target)))
        return infos

    async def _retry_batch_after_risk(self, targets: list[Target], status_code: int):
        from ..core.http import HttpClient

        logger.warning(f"直播接口触发风控 ({status_code})，正在切换账号后重试...")
        if not await HttpClient.invalidate_current_account(status_code=status_code):
            raise Exception(f"Live API risk control: {status_code}")
        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            label=f"直播风控切换账号后重试 {len(targets)} 个 UID",
            params={"uids[]": targets},
            timeout=10.0,
        )
        if res.status_code in {403, 412}:
            await HttpClient.invalidate_current_account(status_code=res.status_code)
            raise Exception(f"Live API risk control after retry: {res.status_code}")
        res.raise_for_status()
        res_dict = res.json()
        if res_dict["code"] != 0:
            if str(res_dict["code"]) in {"-352", "352", "403", "412"}:
                await HttpClient.invalidate_current_account(
                    status_code=int(res_dict["code"])
                )
            raise Exception(f"Live API Error after retry: {res_dict['code']}")
        data = res_dict.get("data", {})
        return [
            type_validate_python(self.Info, data[target])
            if target in data.keys()
            else self._gen_empty_info(int(target))
            for target in targets
        ]

    def compare_status(
        self, target: Target, old_status: Info, new_status: Info
    ) -> list[RawPost]:
        action = new_status.get_live_action(old_status)
        if action == BilibiliLive.LiveAction.TURN_ON:
            return [self._gen_current_status(new_status, 1)]
        elif action == BilibiliLive.LiveAction.TITLE_UPDATE:
            return [self._gen_current_status(new_status, 2)]
        elif action == BilibiliLive.LiveAction.TURN_OFF:
            return [self._gen_current_status(new_status, 3)]
        return []

    def _gen_current_status(self, new_status: Info, category: int):
        status = deepcopy(new_status)
        status.category = Category(category)
        return status

    async def parse(self, raw_post: Info) -> Post:
        url = f"https://live.bilibili.com/{raw_post.room_id}"
        pic = (
            [raw_post.cover]
            if raw_post.category == Category(1)
            else [raw_post.keyframe or raw_post.cover]
        )
        cat_name = self.categories[raw_post.category].replace("提醒", "")
        title = f"[{cat_name}] {raw_post.title}"

        return Post(
            platform=self.platform_name,
            content=f"{raw_post.area_name}",
            title=title,
            timestamp=int(raw_post.live_time),
            url=url,
            images=list(pic),
            nickname=raw_post.uname,
            avatar=raw_post.face,
            id=f"live_{raw_post.room_id}_{raw_post.live_time}_{raw_post.live_status}",
            category=raw_post.category,
        )

    def get_tags(self, raw_post) -> list[Tag]:
        return []

    def get_category(self, raw_post) -> Category:
        return raw_post.category

    async def fetch_new_post(self, sub_unit):
        return []
