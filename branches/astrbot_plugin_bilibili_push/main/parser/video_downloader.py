from __future__ import annotations

import re
import time
from pathlib import Path

from ..core.http import HttpClient
from ..core.network_retry import get_with_retry
from ..utils.logger import logger


class BilibiliVideoDownloader:
    def __init__(
        self,
        download_dir: Path,
        *,
        max_size_mb: int = 30,
        timeout_sec: int = 30,
        quality: int = 16,
    ):
        self.download_dir = Path(download_dir)
        self.max_bytes = max(1, int(max_size_mb)) * 1024 * 1024
        self.timeout_sec = max(5, int(timeout_sec))
        self.quality = int(quality)

    async def download_for_parse(self, info: dict) -> Path | None:
        if info.get("type") != "video":
            return None
        bvid = str(info.get("bvid") or "")
        cid = str(info.get("cid") or "")
        if not bvid or not cid:
            logger.warning("解析视频缺少 bvid 或 cid，跳过视频附件下载")
            return None

        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_files()
        target = self.download_dir / f"{_safe_name(bvid)}_{_safe_name(cid)}.mp4"
        if target.exists() and 0 < target.stat().st_size <= self.max_bytes:
            return target

        source = await self._get_video_source(bvid, cid)
        if not source:
            return None
        url, declared_size = source
        if declared_size and declared_size > self.max_bytes:
            logger.info(
                "解析视频附件超过大小限制，跳过下载: "
                f"{declared_size / 1024 / 1024:.1f}MB > "
                f"{self.max_bytes / 1024 / 1024:.1f}MB"
            )
            return None

        return await self._download_url(url, target, bvid)

    async def _get_video_source(self, bvid: str, cid: str) -> tuple[str, int] | None:
        client = await HttpClient.get_client()
        referer = f"https://www.bilibili.com/video/{bvid}"
        response = await get_with_retry(
            client,
            "https://api.bilibili.com/x/player/playurl",
            label=f"获取视频下载直链 {bvid}",
            params={
                "bvid": bvid,
                "cid": cid,
                "qn": self.quality,
                "fnval": 0,
                "fourk": 0,
            },
            headers={"Referer": referer},
            timeout=10.0,
        )
        data = response.json()
        if data.get("code") != 0:
            logger.warning(f"获取视频下载直链失败: {data.get('message')}")
            return None

        entries = data.get("data", {}).get("durl") or []
        if not entries:
            logger.warning("Bilibili playurl 未返回可直接发送的 durl 视频")
            return None
        entry = entries[0]
        url = entry.get("url")
        if not url:
            return None
        return str(url), int(entry.get("size") or 0)

    async def _download_url(self, url: str, target: Path, bvid: str) -> Path | None:
        client = await HttpClient.get_client()
        temp_path = target.with_suffix(".download")
        downloaded = 0
        headers = {"Referer": f"https://www.bilibili.com/video/{bvid}"}
        try:
            async with client.stream(
                "GET",
                url,
                headers=headers,
                timeout=self.timeout_sec,
            ) as response:
                response.raise_for_status()
                with temp_path.open("wb") as file:
                    async for chunk in response.aiter_bytes():
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > self.max_bytes:
                            raise ValueError("video exceeds size limit")
                        file.write(chunk)
            temp_path.replace(target)
            return target
        except Exception as exc:
            logger.warning(f"解析视频附件下载失败，已跳过: {exc}")
            for path in (temp_path, target):
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass
            return None

    def _cleanup_old_files(self) -> None:
        cutoff = time.time() - 24 * 3600
        for path in self.download_dir.glob("*"):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "video"
