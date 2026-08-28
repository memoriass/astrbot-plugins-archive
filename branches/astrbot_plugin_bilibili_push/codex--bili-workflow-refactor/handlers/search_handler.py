import time
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..core.http import HttpClient
from ..rendering import RendererPort


class SearchHandler:
    def __init__(self, context: Context, bg_dir: Path, renderer: RendererPort):
        self.bg_dir = bg_dir
        self.context = context
        self.renderer = renderer

    async def handle_search(self, event: AstrMessageEvent, keyword: str, star_inst):
        cache_key = f"search_cache_{keyword}"
        cached_data = await star_inst.get_kv_data(cache_key, None)
        now = time.time()

        if cached_data and (
            now - cached_data.get("timestamp", 0)
            < getattr(star_inst, "search_cache_expiry_hours", 24) * 3600
        ):
            search_results = cached_data.get("results", [])
        else:
            yield event.plain_result(f"⏳ 正在 B站 搜索: {keyword}...")
            client = await HttpClient.get_client()
            search_results = []
            try:
                res = await client.get(
                    "https://api.bilibili.com/x/web-interface/search/type",
                    params={"search_type": "bili_user", "keyword": keyword, "page": 1},
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data["code"] == 0:
                        for item in data["data"].get("result", []):
                            search_results.append(
                                {
                                    "uid": str(item["mid"]),
                                    "username": item["uname"],
                                    "face": "https:" + item["upic"]
                                    if not item["upic"].startswith("http")
                                    else item["upic"],
                                    "is_live": False,
                                    "has_live": True,
                                    "has_dynamic": True,
                                }
                            )
                if search_results:
                    await star_inst.put_kv_data(
                        cache_key, {"results": search_results, "timestamp": now}
                    )
            except Exception as e:
                logger.error(f"Search failed: {e}")
                yield event.plain_result(f"❌ 搜索失败: {e}")
                return

        if not search_results:
            yield event.plain_result(f"🔍 未找到 '{keyword}'")
            return
        yield event.plain_result(f"🔍 找到 {len(search_results)} 位相关 UP 主")

        try:
            img_bytes = await self.renderer.render(
                "sub_list.html.jinja",
                {
                    "subs": search_results[:12],
                    "page_title": f"搜索结果: {keyword}",
                },
                viewport={"width": 1000, "height": 800},
                selector=".card-board",
            )
            yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
        except Exception as e:
            logger.error(f"Search render failed: {e}")
            yield event.plain_result("❌ 搜索结果渲染失败")
