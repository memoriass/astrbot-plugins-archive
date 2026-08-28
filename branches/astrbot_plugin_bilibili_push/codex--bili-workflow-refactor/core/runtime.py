import asyncio
import os
import shutil
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import MessageChain

from .http import HttpClient


class PluginRuntime:
    def __init__(self, star):
        self.star = star
        self.cleanup_task: asyncio.Task | None = None

    def init_resources(self):
        default_bg_dir = self.star.plugin_dir / "utils" / "resources" / "backgrounds"
        if not default_bg_dir.exists():
            return

        for root, _, files in os.walk(default_bg_dir):
            for file in files:
                if not file.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                src_file = Path(root) / file
                rel_path = src_file.relative_to(default_bg_dir)
                dst_file = self.star.bg_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                if dst_file.exists():
                    continue
                try:
                    shutil.copy2(src_file, dst_file)
                    logger.debug(f"已复制初始背景图: {rel_path}")
                except Exception as exc:
                    logger.warning(f"复制初始背景图失败 {file}: {exc}")

    async def start(self):
        await HttpClient.set_star_instance(self.star)
        await self.star.scheduler.start()
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self.cleanup_temp_files())

    async def stop(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
        await self.star.scheduler.terminate()
        await HttpClient.close()

    async def cleanup_temp_files(self):
        while True:
            try:
                now = time.time()
                for file in self.star.temp_dir.iterdir():
                    if file.is_file() and now - file.stat().st_mtime > 3600:
                        os.remove(file)
            except Exception as exc:
                logger.warning(f"临时文件清理失败: {exc}")
            await asyncio.sleep(1800)

    async def handle_new_post(self, platform: str, target_id: str, msgs: list):
        try:
            logger.info(f"Bilibili 正在执行最终推送: {target_id} | 消息段: {len(msgs)}")
            chain = MessageChain(chain=msgs)
            await self.star.context.send_message(target_id, chain)
            logger.info(f"Bilibili 推送任务已提交给框架: {target_id}")
        except Exception as exc:
            logger.error(f"Bilibili 推送消息失败 ({target_id}): {exc}")
