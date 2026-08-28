"""
媒体处理模块
提供 Emby、Plex、Jellyfin 数据转换、标准化和数据丰富功能
"""

import html
import time
import os
import base64
import random
from pathlib import Path

from astrbot.api import logger

from .enrichment import EnrichmentManager
from .processors import ProcessorManager


class MediaHandler:
    def __init__(self, config: dict | None = None):
        self.processor_manager = ProcessorManager()
        self.enrichment_manager = EnrichmentManager(config)

    def detect_media_source(self, data: dict, headers: dict) -> str:
        """检测媒体通知来源"""
        try:
            return self.processor_manager.detect_source(data, headers)
        except Exception as e:
            logger.error(f"媒体来源检测失败: {e}")
            return "generic"

    async def process_media_data(
        self, raw_data: dict, source: str, headers: dict
    ) -> dict:
        """处理媒体通知的核心逻辑"""
        try:
            # 1. 转换为标准格式
            media_data = self.processor_manager.convert_to_standard(raw_data, source, headers)
            if not media_data:
                return self.create_fallback_payload(raw_data, source)

            # 2. 自动进行多源数据丰富
            custom_image_url = media_data.get("image_url", "")
            enriched_data = await self.enrichment_manager.enrich_media_data(media_data)

            # 3. 获取图片决策逻辑
            enricher_image_url = await self.enrichment_manager.get_media_image(enriched_data)
            
            if enricher_image_url:
                enriched_data["image_url"] = enricher_image_url
            elif custom_image_url:
                enriched_data["image_url"] = custom_image_url
            else:
                enriched_data["image_url"] = self._get_random_bg()

            return self.create_message_payload(enriched_data, source)

        except Exception as e:
            logger.error(f"处理媒体数据失败: {e}")
            return self.create_fallback_payload(raw_data, source)

    def create_message_payload(self, media_data: dict, source: str) -> dict:
        """创建标准消息载荷"""
        return {
            "image_url": media_data.get("image_url", ""),
            "message_text": self.generate_message_text(media_data),
            "source": source,
            "media_data": media_data,
            "timestamp": time.time(),
        }

    def generate_message_text(self, data: dict) -> str:
        """生成渲染文本内容"""
        tp = data.get("item_type", "")
        parts = []
        
        processor = self.processor_manager.get_processor("generic")
        cn_tp = processor.get_media_type_display(tp)
        parts.append(f"新剧集上线" if tp == "Episode" else f"新{cn_tp}上线")

        sn, itm, yr = data.get("series_name"), data.get("item_name"), data.get("year")
        if tp == "Movie":
            parts.append(f"名称: {itm or sn}{f' ({yr})' if yr else ''}")
        elif tp == "Episode":
            if sn: parts.append(f"剧集: {sn}{f' ({yr})' if yr else ''}")
            s, e = data.get("season_number"), data.get("episode_number")
            if s and e: parts.append(f"集号: S{str(s).zfill(2)}E{str(e).zfill(2)}")
            if itm: parts.append(f"集名: {itm}")
        else:
            parts.append(f"名称: {itm or sn}{f' ({yr})' if yr else ''}")

        ov = data.get("overview")
        if ov:
            ov_clean = html.unescape(ov).split("\n")[0].split("。")[0]
            parts.append(f"剧情: {ov_clean[:200]}...")

        if data.get("tmdb_enriched"): parts.append("[*] 数据来源: TMDB")
        elif data.get("bgm_enriched"): parts.append("[*] 数据来源: BGM.TV")

        return "\n".join(parts)

    def create_fallback_payload(self, raw_data: dict, source: str) -> dict:
        return {
            "image_url": "",
            "message_text": f"来自 {source.title()} 的媒体通知",
            "source": source,
            "media_data": raw_data,
            "timestamp": time.time(),
        }

    def _get_random_bg(self) -> str:
        """获取本地随机背景图"""
        try:
            db_dir = getattr(self.enrichment_manager.cache, "db_dir", None)
            if not db_dir:
                 root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                 db_dir = os.path.join(root_dir, "data")
            
            bg_dir = Path(db_dir) / "media_bg"
            if not bg_dir.exists(): return ""

            matches = [f for f in bg_dir.iterdir() if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]]
            if not matches: return ""
            
            selected = random.choice(matches)
            with open(selected, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                ext = selected.suffix.lower().replace(".", "").replace("jpg", "jpeg")
                return f"data:image/{ext};base64,{b64}"
        except: return ""

    def validate_media_data(self, media_data: dict) -> bool:
        return self.processor_manager.get_processor("generic").validate_standard_data(media_data)
