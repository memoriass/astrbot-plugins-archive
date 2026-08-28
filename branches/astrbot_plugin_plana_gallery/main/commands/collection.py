from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from PIL import Image as PillowImage


class SilentChatCollectionMixin:
    @filter.event_message_type(filter.EventMessageType.ALL, priority=20)
    async def collect_chat_images_silently(self, event: AstrMessageEvent) -> None:
        if not self.enabled or not self.enable_silent_chat_image_collection:
            return
        if _is_private(event) or _sender_key(event) in self.pending_uploads:
            return
        scope = _scope(event)
        if not scope or not _scope_allowed(scope, self.silent_collection_scope_allowlist):
            return
        images = _event_images(event)[: self.silent_collection_max_images_per_message]
        if not images:
            return
        scope_hash = _hash(scope)
        counts = self.store.chat_collection_counts(
            scope_hash=scope_hash,
            since=self.store._now() - 86400,
        )
        if counts["scope"] >= self.silent_collection_daily_limit_per_scope:
            return
        if counts["global"] >= self.silent_collection_global_daily_limit:
            return
        sender_hash = _hash(str(event.get_sender_id() or ""))
        message_hash = _hash(_message_identity(event))
        for index, image in enumerate(images, 1):
            if counts["scope"] >= self.silent_collection_daily_limit_per_scope:
                break
            if counts["global"] >= self.silent_collection_global_daily_limit:
                break
            try:
                content, filename = await self._silent_image_content(image, index=index)
                await asyncio.to_thread(
                    _validate_image,
                    content,
                    self.silent_collection_max_pixels,
                    self.silent_collection_max_gif_frames,
                )
                hash_status, result = await self._import_silent_content(content, filename)
                if hash_status["status"] != "new":
                    asset = hash_status.get("asset") or {}
                    self.store.record_chat_collection(
                        scope_hash=scope_hash,
                        sender_hash=sender_hash,
                        message_hash=message_hash,
                        asset_ref=str(asset.get("asset_ref") or hash_status.get("asset_ref") or ""),
                        outcome=(
                            "duplicate" if hash_status["status"] == "existing" else "rejected"
                        ),
                        reason="" if hash_status["status"] == "existing" else "tombstoned",
                    )
                    continue
                if not result.get("ok"):
                    self.store.record_chat_collection(
                        scope_hash=scope_hash,
                        sender_hash=sender_hash,
                        message_hash=message_hash,
                        outcome="rejected",
                        reason=str(result.get("error") or "import_failed"),
                    )
                    continue
                asset = result.get("asset") or {}
                created = bool(result.get("created"))
                self.store.record_chat_collection(
                    scope_hash=scope_hash,
                    sender_hash=sender_hash,
                    message_hash=message_hash,
                    asset_ref=str(asset.get("asset_ref") or ""),
                    outcome="collected" if created else "duplicate",
                )
                if created:
                    counts["scope"] += 1
                    counts["global"] += 1
            except ValueError as exc:
                self.store.record_chat_collection(
                    scope_hash=scope_hash,
                    sender_hash=sender_hash,
                    message_hash=message_hash,
                    outcome="rejected",
                    reason=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Plana Gallery silent collection failed: %s", exc)
                self.store.record_chat_collection(
                    scope_hash=scope_hash,
                    sender_hash=sender_hash,
                    message_hash=message_hash,
                    outcome="failed",
                    reason=type(exc).__name__,
                )

    async def _import_silent_content(
        self,
        content: bytes,
        filename: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        async with self._silent_collection_lock:
            digest = hashlib.sha256(content).hexdigest()
            hash_status = await asyncio.to_thread(
                self.store.chat_collection_hash_status,
                digest,
            )
            if hash_status["status"] != "new":
                return hash_status, {}
            result = await asyncio.to_thread(
                self.store.import_bytes,
                content,
                filename=filename,
                source="chat-silent",
                original_path="",
            )
            return hash_status, result

    async def _silent_image_content(self, image: Image, *, index: int) -> tuple[bytes, str]:
        local_path = _image_local_path(image)
        if local_path:
            size = local_path.stat().st_size
            if size > self.silent_collection_max_bytes:
                raise ValueError("file_too_large")
            return await asyncio.to_thread(local_path.read_bytes), local_path.name
        url = str(getattr(image, "url", "") or getattr(image, "file", "") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("image_url_invalid")
        timeout = aiohttp.ClientTimeout(total=max(3, self.chat_download_timeout_seconds))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status >= 400:
                    raise ValueError(f"download_http_{response.status}")
                content_length = int(response.headers.get("Content-Length") or 0)
                if content_length > self.silent_collection_max_bytes:
                    raise ValueError("file_too_large")
                body = bytearray()
                async for chunk in response.content.iter_chunked(256 * 1024):
                    body.extend(chunk)
                    if len(body) > self.silent_collection_max_bytes:
                        raise ValueError("file_too_large")
        filename = Path(parsed.path).name or f"chat_image_{index}"
        return bytes(body), filename


def _validate_image(content: bytes, max_pixels: int, max_gif_frames: int) -> None:
    if not content:
        raise ValueError("empty_file")
    try:
        with PillowImage.open(io.BytesIO(content)) as image:
            width, height = image.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise ValueError("image_pixels_exceeded")
            if int(getattr(image, "n_frames", 1) or 1) > max_gif_frames:
                raise ValueError("gif_frames_exceeded")
            image.verify()
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid_image") from exc


def _is_private(event: AstrMessageEvent) -> bool:
    checker = getattr(event, "is_private_chat", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            pass
    return "group" not in str(getattr(event, "unified_msg_origin", "") or "").lower()


def _scope(event: AstrMessageEvent) -> str:
    return str(getattr(event, "unified_msg_origin", "") or event.get_session_id() or "").strip()


def _scope_allowed(scope: str, allowlist: set[str]) -> bool:
    if not allowlist:
        return True
    return any(
        item == scope or scope.endswith(f":{item}") or f":{item}:" in scope
        for item in allowlist
    )


def _sender_key(event: AstrMessageEvent) -> str:
    return f"{getattr(event, 'unified_msg_origin', '')}:{event.get_session_id()}:{event.get_sender_id()}"


def _event_images(event: AstrMessageEvent) -> list[Image]:
    message_obj = getattr(event, "message_obj", None)
    return [item for item in (getattr(message_obj, "message", []) or []) if isinstance(item, Image)]


def _image_local_path(image: Image) -> Path | None:
    for attr in ("path", "file"):
        value = str(getattr(image, attr, "") or "").strip()
        if value and not value.startswith(("http://", "https://")):
            path = Path(value).expanduser()
            if path.is_file():
                return path
    return None


def _message_identity(event: AstrMessageEvent) -> str:
    message_obj = getattr(event, "message_obj", None)
    message_id = str(getattr(message_obj, "message_id", "") or "")
    return f"{_scope(event)}:{event.get_sender_id()}:{message_id}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
