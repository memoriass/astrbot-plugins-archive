"""Bilibili 动态平台实现"""

import json
import time
from typing import ClassVar

from ..core.compat import type_validate_json
from ..core.models import DynRawPost, PostAPI, UserAPI
from ..core.network_retry import get_with_retry
from ..core.platform import NewMessagePlatform
from ..core.types import ApiError, Category, Post, Target
from ..core.utils import wbi_sign
from ..utils.logger import logger
from .fallback import FallbackCardConverter
from .post_parser import DynamicPostParser


class BilibiliDynamic(DynamicPostParser, FallbackCardConverter, NewMessagePlatform):
    platform_name = "bilibili"
    name = "B站"
    categories: ClassVar[dict[Category, str]] = {
        1: "一般动态",
        2: "专栏文章",
        3: "视频",
        4: "纯文字",
        5: "转发",
        6: "直播推送",
    }

    _wbi_keys: tuple[str, str] | None = None
    _wbi_keys_time: float = 0

    async def _get_wbi_keys(self) -> tuple[str, str]:
        if self._wbi_keys and time.time() - self._wbi_keys_time < 3600:
            return self._wbi_keys

        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.bilibili.com/x/web-interface/nav",
            label="获取 WBI Keys",
        )
        res_json = res.json()
        if "data" not in res_json or "wbi_img" not in res_json["data"]:
            raise ApiError(f"获取 WBI Keys 失败: {res_json.get('message', '未知错误')}")

        data = res_json["data"]["wbi_img"]
        img_key = data["img_url"].split("/")[-1].split(".")[0]
        sub_key = data["sub_url"].split("/")[-1].split(".")[0]

        self._wbi_keys = (img_key, sub_key)
        self._wbi_keys_time = time.time()
        return self._wbi_keys

    async def get_target_name(self, target: Target) -> str | None:
        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.bilibili.com/x/web-interface/card",
            label=f"获取动态目标名称 {target}",
            params={"mid": target},
        )
        if res.status_code != 200:
            res = await get_with_retry(
                client,
                "https://api.live.bilibili.com/live_user/v1/Master/info",
                label=f"获取动态目标备用名称 {target}",
                params={"uid": target},
            )
            if res.status_code != 200:
                return None

        res_data = type_validate_json(UserAPI, res.content)
        if res_data.code != 0 or not res_data.data:
            return None

        if res_data.data.card:
            return res_data.data.card.name
        if res_data.data.info:
            return res_data.data.info.uname or res_data.data.info.name
        return None

    async def get_sub_list(self, target: Target) -> list[DynRawPost]:
        posts = await self._try_polymer_then_fallback(target)
        if posts:
            posts.sort(key=lambda x: x.modules.module_author.pub_ts, reverse=True)
        return posts

    async def _try_polymer_then_fallback(self, target: Target) -> list[DynRawPost]:
        try:
            posts = await self._get_sub_list_polymer(target)
            from ..core.http import HttpClient

            await HttpClient.set_current_account_status(valid=True, status_code=None)
            if posts:
                return posts
            logger.debug(f"Polymer 接口返回空动态列表 {target}")
            return []
        except ApiError as exc:
            posts = await self._retry_after_risk_control(
                exc, target, self._get_sub_list_polymer
            )
            if posts is not None:
                return posts
            logger.warning(f"Polymer 接口失败 ({exc})，尝试备用接口...")
        except Exception as exc:
            logger.warning(f"Polymer 接口异常 ({exc})，尝试备用接口...")

        return await self._fallback_with_retry(target)

    async def _fallback_with_retry(self, target: Target) -> list[DynRawPost]:
        try:
            return await self._get_sub_list_fallback(target)
        except Exception as exc:
            posts = await self._retry_after_risk_control(
                exc, target, self._get_sub_list_fallback
            )
            if posts is not None:
                return posts
            logger.error(f"备用接口抓取也失败了: {exc}")
            raise ApiError(f"获取动态列表失败: {exc}") from exc

    async def _retry_after_risk_control(
        self, exc: Exception, target: Target, fetcher
    ) -> list[DynRawPost] | None:
        err_msg = str(exc)
        if not any(code in err_msg for code in ("352", "412", "403")):
            return None

        from ..core.http import HttpClient

        status_code = 412 if "412" in err_msg else (352 if "352" in err_msg else 403)
        logger.warning(f"检测到 B站 风控 ({err_msg})，正在自动切换账号...")
        if not await HttpClient.invalidate_current_account(status_code=status_code):
            return None

        try:
            posts = await fetcher(target)
            return posts if posts else None
        except Exception as retry_exc:
            logger.warning(f"接口切换账号后重试失败: {retry_exc}")
            return None

    async def _get_sub_list_polymer(self, target: Target) -> list[DynRawPost]:
        client = await self.get_client()
        params = {"host_mid": target, "features": "itemOpusStyle"}

        img_key, sub_key = await self._get_wbi_keys()
        signed_params = wbi_sign(params.copy(), img_key, sub_key)
        res = await get_with_retry(
            client,
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
            label=f"获取动态列表 Polymer {target}",
            params=signed_params,
            headers={"Referer": f"https://space.bilibili.com/{target}/dynamic"},
            timeout=10.0,
        )
        if res.status_code == 412:
            raise ApiError("412 Precondition Failed")

        res.raise_for_status()
        res_obj = type_validate_json(PostAPI, res.content)
        if res_obj.code == 0:
            if (data := res_obj.data) and (items := data.items):
                return [item for item in items if item.type != "DYNAMIC_TYPE_NONE"]
            return []
        if res_obj.code == -352:
            raise ApiError("Risk Control -352")
        raise ApiError(f"Polymer Code {res_obj.code}")

    async def _get_sub_list_fallback(self, target: Target) -> list[DynRawPost]:
        client = await self.get_client()
        res = await get_with_retry(
            client,
            "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history",
            label=f"获取动态列表 Fallback {target}",
            params={
                "host_uid": target,
                "offset_dynamic_id": 0,
                "need_top": 0,
                "platform": "web",
            },
            headers={"Referer": f"https://space.bilibili.com/{target}/dynamic"},
            timeout=10.0,
        )
        res.raise_for_status()
        data = res.json()
        if data["code"] != 0:
            raise ApiError(f"Fallback Code {data['code']}")

        converted_posts = []
        for card in data.get("data", {}).get("cards", []):
            try:
                desc = card.get("desc", {})
                card_json = json.loads(card.get("card", "{}"))
                post = self._convert_fallback_card(desc, card_json)
                if post:
                    converted_posts.append(post)
            except Exception as exc:
                logger.debug(f"Failed to convert fallback card: {exc}")
        return converted_posts

    async def fetch_new_post(self, sub_unit) -> list[Post]:
        raw_posts = await self.get_sub_list(sub_unit.sub_target)
        posts = []
        for raw_post in raw_posts:
            posts.append(await self.parse(raw_post))
        return posts
