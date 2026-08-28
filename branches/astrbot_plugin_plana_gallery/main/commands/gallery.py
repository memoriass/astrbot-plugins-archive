from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.core.star.filter.command import GreedyStr

class GalleryCommandMixin:
    @filter.command_group("图库")
    def gallery(self):
        """Plana Gallery command group."""

    @gallery.command("help")
    @gallery.command("帮助")
    async def gallery_help(self, event: AstrMessageEvent):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        yield event.plain_result(
            "Plana Gallery 命令：\n"
            "  /图库 查看 [标签] - 查看图库概览或指定标签图片\n"
            "  /图库 搜索 <关键词> - 搜索标题、说明和标签\n"
            "  /图库 随机 [标签或关键词] - 随机发送一张图\n"
            "  /图库 发送 <id|asset_ref|关键词> - 发送指定图片\n"
            "  /图库 收图 [tag1,tag2] - 管理员在聊天中收图\n"
            "  /图库 导入 <本地路径> [tags=tag1,tag2] - 管理员导入本地图片\n"
            "  /图库 删除 <id|asset_ref> confirm - 管理员删除资产\n"
            "  /图库 统计 - 查看本地资产和标签数量\n"
            "  /图库 统计 - 查看图库统计\n"
            "Web: /api/plug/plana_gallery/dashboard"
        )

    @gallery.command("查看")
    async def gallery_list(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        text = str(value or "").strip().lstrip("#")
        if text:
            assets = self.store.list_assets(query="", tag=text, limit=15)
            if not assets:
                assets = self.store.list_assets(query=text, limit=15)
            if not assets:
                yield event.plain_result(f"未找到标签或关键词「{text}」对应的图片。")
                return
            yield event.plain_result(_format_asset_list(assets, title=f"图库：{text}"))
            return
        status = self.store.status()
        recent = self.store.list_assets(limit=8)
        tags = ", ".join(status.get("tag_list", [])[:30]) or "暂无"
        body = [
            f"图库资产：{status.get('assets', 0)} 张，标签：{status.get('tags', 0)} 个",
            f"标签：{tags}",
        ]
        if recent:
            body.append("")
            body.append(_format_asset_list(recent, title="最近更新"))
        yield event.plain_result("\n".join(body))

    @gallery.command("搜索")
    async def gallery_search(self, event: AstrMessageEvent, query: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        text = str(query or "").strip()
        if not text:
            yield event.plain_result("用法：/图库 搜索 <关键词>")
            return
        assets = self.store.list_assets(query=text, limit=15)
        if not assets:
            yield event.plain_result(f"未搜索到「{text}」。")
            return
        yield event.plain_result(_format_asset_list(assets, title=f"搜索：{text}"))

    @gallery.command("随机")
    async def gallery_random(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        text = str(value or "").strip().lstrip("#")
        tag_list = set(self.store.status().get("tag_list", []))
        asset = self.store.random_asset(
            tag=text if text in tag_list else "",
            query="" if text in tag_list else text,
        )
        if not asset:
            yield event.plain_result("图库里还没有可发送的图片。")
            return
        yield self._asset_image_result(event, asset)

    @gallery.command("发送")
    async def gallery_send(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        text = str(value or "").strip()
        if not text:
            yield event.plain_result("用法：/图库 发送 <id|asset_ref|关键词>")
            return
        asset = self._find_asset(text)
        if not asset:
            yield event.plain_result(f"未找到图片：{text}")
            return
        yield self._asset_image_result(event, asset)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gallery.command("导入")
    async def gallery_import(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        path_text, tags = _split_tags_suffix(str(value or "").strip())
        if not path_text:
            yield event.plain_result("用法：/图库 导入 <本地图片路径> [tags=tag1,tag2]")
            return
        result = self.store.import_asset(
            path_text,
            tags=tags,
            source="command",
            keep_original_path=self.allow_original_path,
        )
        if not result.get("ok"):
            yield event.plain_result(f"导入失败：{result.get('error', 'unknown')}")
            return
        asset = result.get("asset") or {}
        yield event.plain_result(
            f"已导入：{asset.get('asset_ref')}，id={asset.get('id')}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gallery.command("收图")
    async def gallery_collect(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        if not self.allow_chat_image_import:
            yield event.plain_result("聊天收图当前已禁用。")
            return
        key = _sender_key(event)
        tags = _tags(value)
        self.pending_uploads[key] = {
            "tags": tags,
            "expires_at": time.time() + max(5, self.upload_wait_seconds),
        }
        tag_text = f" 标签：{', '.join(tags)}" if tags else ""
        yield event.plain_result(
            f"请在 {self.upload_wait_seconds} 秒内发送要收录的图片。{tag_text}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @gallery.command("删除")
    async def gallery_delete(self, event: AstrMessageEvent, value: GreedyStr = ""):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        text = str(value or "").strip()
        identifier, confirmed = _split_confirm_suffix(text)
        if not identifier:
            yield event.plain_result("用法：/图库 删除 <id|asset_ref> confirm")
            return
        asset = self._find_asset(identifier)
        if not asset:
            yield event.plain_result(f"未找到图片：{identifier}")
            return
        if not confirmed:
            yield event.plain_result(
                "删除会移除图库记录和托管副本。确认请发送："
                f"/图库 删除 {asset['id']} confirm"
            )
            return
        result = self.store.delete_asset(int(asset["id"]))
        if not result.get("ok"):
            yield event.plain_result(f"删除失败：{result.get('error', 'unknown')}")
            return
        yield event.plain_result(f"已删除：{asset.get('asset_ref')}")

    @gallery.command("统计")
    async def gallery_stats(self, event: AstrMessageEvent):
        if not self._commands_enabled():
            yield event.plain_result("图库命令当前已禁用。")
            return
        status = self.store.status()
        tag_text = ", ".join(status.get("tag_list", [])[:50]) or "暂无"
        yield event.plain_result(
            f"图库统计：{status.get('assets', 0)} 张图片，"
            f"{status.get('tags', 0)} 个标签。\n标签：{tag_text}"
        )

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10)
    async def handle_pending_upload(self, event: AstrMessageEvent):
        if not self._commands_enabled() or not self.allow_chat_image_import:
            return
        key = _sender_key(event)
        state = self.pending_uploads.get(key)
        if not state:
            return
        text = str(event.get_message_str() or "").strip()
        if text.startswith("/"):
            return
        if time.time() > float(state.get("expires_at", 0)):
            self.pending_uploads.pop(key, None)
            yield event.plain_result("收图等待已超时，请重新发送 /图库 收图。")
            return
        if text.lower() in {"取消", "cancel"}:
            self.pending_uploads.pop(key, None)
            event.stop_event()
            yield event.plain_result("已取消本次收图。")
            return
        images = _event_images(event)
        if not images:
            event.stop_event()
            yield event.plain_result("请发送图片，或发送“取消”结束本次收图。")
            return
        imported = []
        errors = []
        for index, image in enumerate(images, 1):
            try:
                result = await self._import_message_image(
                    image,
                    index=index,
                    tags=list(state.get("tags", [])),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana Gallery chat import failed: %s", exc)
                errors.append(str(exc))
                continue
            if result.get("ok"):
                imported.append(result.get("asset") or {})
            else:
                errors.append(str(result.get("error", "unknown")))
        self.pending_uploads.pop(key, None)
        event.stop_event()
        if not imported:
            yield event.plain_result(f"收图失败：{'; '.join(errors) or 'unknown'}")
            return
        refs = ", ".join(str(asset.get("asset_ref")) for asset in imported[:5])
        suffix = f"；失败 {len(errors)} 张" if errors else ""
        yield event.plain_result(f"已收录 {len(imported)} 张图片：{refs}{suffix}")

    def _commands_enabled(self) -> bool:
        return self.enabled and self.enable_commands

    def _find_asset(self, text: str) -> dict[str, Any] | None:
        asset = self.store.resolve_asset(text)
        if asset:
            return asset
        matches = self.store.list_assets(query=text, limit=1)
        return matches[0] if matches else None

    def _asset_image_result(self, event: AstrMessageEvent, asset: dict[str, Any]):
        asset_file = self.store.file_for_asset(int(asset.get("id", 0)))
        if asset_file is None:
            return event.plain_result("图片文件不存在，可能需要重新导入。")
        path, _mime_type = asset_file
        return event.result([Image.fromFileSystem(str(path))])

    async def _import_message_image(
        self,
        image: Image,
        *,
        index: int,
        tags: list[str],
    ) -> dict[str, Any]:
        local_path = _image_local_path(image)
        if local_path:
            return self.store.import_asset(
                str(local_path),
                tags=tags,
                source="chat",
                keep_original_path=self.allow_original_path,
            )
        content, filename = await self._download_image(image, index=index)
        return self.store.import_bytes(
            content,
            filename=filename,
            tags=tags,
            source="chat",
        )

    async def _download_image(self, image: Image, *, index: int) -> tuple[bytes, str]:
        url = str(getattr(image, "url", "") or getattr(image, "file", "") or "")
        if not url:
            raise ValueError("image_url_missing")
        if "multimedia.nt.qq.com.cn" in url and url.startswith("https://"):
            url = url.replace("https://", "http://", 1)
        timeout = aiohttp.ClientTimeout(total=max(3, self.chat_download_timeout_seconds))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, ssl=False) as resp:
                if resp.status >= 400:
                    raise ValueError(f"download_http_{resp.status}")
                body = bytearray()
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    body.extend(chunk)
                    if len(body) > self.store.max_import_bytes:
                        raise ValueError("file_too_large")
        filename = Path(unquote(urlparse(url).path)).name or f"chat_image_{index}"
        return bytes(body), filename


def _tags(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\n", ",").replace("，", ",").replace("、", ",").split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _sender_key(event: AstrMessageEvent) -> str:
    return (
        f"{getattr(event, 'unified_msg_origin', '')}:"
        f"{event.get_session_id()}:"
        f"{event.get_sender_id()}"
    )


def _event_images(event: AstrMessageEvent) -> list[Image]:
    message_obj = getattr(event, "message_obj", None)
    message = getattr(message_obj, "message", []) or []
    return [item for item in message if isinstance(item, Image)]


def _image_local_path(image: Image) -> Path | None:
    for attr in ("path", "file"):
        value = str(getattr(image, attr, "") or "")
        if not value:
            continue
        if value.startswith("file://"):
            candidate = Path(unquote(urlparse(value).path))
        else:
            candidate = Path(value)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _format_asset_list(assets: list[dict[str, Any]], *, title: str) -> str:
    lines = [title]
    for asset in assets:
        tags = ", ".join(asset.get("tags", [])[:6]) or "无标签"
        name = asset.get("title") or asset.get("asset_ref")
        lines.append(f"- {asset.get('id')}: {name} [{tags}] {asset.get('asset_ref')}")
    return "\n".join(lines)


def _split_tags_suffix(text: str) -> tuple[str, list[str]]:
    for marker in (" tags=", " 标签="):
        if marker in text:
            path, raw_tags = text.rsplit(marker, 1)
            return path.strip().strip('"'), _tags(raw_tags)
    return text.strip().strip('"'), []


def _split_confirm_suffix(text: str) -> tuple[str, bool]:
    lowered = text.lower().strip()
    for marker in (" confirm", " 确认"):
        if lowered.endswith(marker):
            return text[: -len(marker)].strip(), True
    return text.strip(), False
