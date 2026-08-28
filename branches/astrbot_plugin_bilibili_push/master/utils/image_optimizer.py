from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from .logger import logger


_IMAGE_FETCH_TIMEOUT_SEC = 8
_DEFAULT_MAX_SOURCE_BYTES = 16 * 1024 * 1024
AVATAR_IMAGE_CACHE_TTL_SEC = 24 * 3600
IMAGE_CACHE_UNUSED_RETENTION_SEC = 120 * 24 * 3600
_IMAGE_CACHE_CLEANUP_INTERVAL_SEC = 24 * 3600
_AVATAR_FIELD_NAMES = {"avatar", "face"}
_COVER_FIELD_NAMES = {"cover"}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)
TRANSPARENT_IMAGE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
DEFAULT_AVATAR_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAABn0lEQVR42u3dQU7DQAyF4dTq4dghcVAkdj0VCzYs4QhFIhN77O+tq8Z+f/ySdCbq7fPr++egNAULAACAAACAAACAAACAAACAAACAAACAAACAAACAAACA1ui+W8HvH4+nn3l7fdmmn9sO21L+YvquMEoD+I/xu4CICeav+L7WAFaZVRFCTDG/KoSYZH5FCDHN/GoQYqL5lSDEVPOrHN9PEZMnoEoOZ9ZhAlyEARgdP9n1mAARBAABAAABAAABAMBlqrZInlWPCRBBABzTYyizDhMwPYKypyD7+DE5AipEYEy9Daxy/YmJ9+KVnkHKXYRXm1PtAbDkXdAqkypuUS/3fsAVa7OVQJQBkLEoXgFEOoAKuyPGPgnbGWdfUHo9l0dQ1Xe1siIpmJ9bZzA/t95gfm7dwfzc+i3IHI1/C9r97L+ij2B+bj8iqGMEdTv7V/ZlArpNQNezf1V/JqDTBHQ/+1f0aQIsygNAHQBMyf+z+zUBIggAAgAAAgAAAgAAAgCAo+M/VRxF94+aABEEAHUBMOU6cGafJqBbBHWfgrP7+wXNa5xiXaYydgAAAABJRU5ErkJggg=="
)
_USE_ORIGINAL = object()


@dataclass(frozen=True, slots=True)
class ImageOptimizePolicy:
    max_width: int
    max_height: int
    max_pixels: int
    quality: int = 86
    max_source_bytes: int = _DEFAULT_MAX_SOURCE_BYTES


LIVE_COVER_POLICY = ImageOptimizePolicy(
    max_width=2560,
    max_height=1440,
    max_pixels=2560 * 1440,
    quality=90,
)
DYNAMIC_HERO_POLICY = ImageOptimizePolicy(
    max_width=2560,
    max_height=1600,
    max_pixels=2560 * 1600,
    quality=90,
)
AVATAR_POLICY = ImageOptimizePolicy(
    max_width=512,
    max_height=512,
    max_pixels=512 * 512,
    quality=88,
    max_source_bytes=3 * 1024 * 1024,
)


class ImageTooLarge(ValueError):
    pass


async def optimize_template_image(
    image: Any,
    policy: ImageOptimizePolicy,
    *,
    label: str = "image",
    fallback: Any = _USE_ORIGINAL,
    cache_dir: Path | str | None = None,
    cache_ttl_sec: int = AVATAR_IMAGE_CACHE_TTL_SEC,
    cache_unused_retention_sec: int = IMAGE_CACHE_UNUSED_RETENTION_SEC,
) -> Any:
    if not image:
        return image if fallback is _USE_ORIGINAL else fallback
    cache_path = Path(cache_dir) if cache_dir else None
    stale_cached = ""
    if cache_path and _is_cacheable_image(image):
        cached = await asyncio.to_thread(
            _read_cached_image,
            cache_path,
            image,
            policy,
            cache_ttl_sec,
            cache_unused_retention_sec,
            False,
        )
        if cached:
            return cached
        stale_cached = await asyncio.to_thread(
            _read_cached_image,
            cache_path,
            image,
            policy,
            cache_ttl_sec,
            cache_unused_retention_sec,
            True,
        )

    try:
        optimized = await asyncio.to_thread(_optimize_template_image_sync, image, policy)
        if cache_path and _is_cacheable_result(optimized):
            await asyncio.to_thread(
                _write_cached_image,
                cache_path,
                image,
                policy,
                optimized,
                cache_unused_retention_sec,
            )
        return optimized
    except ImageTooLarge as exc:
        if stale_cached:
            logger.warning(f"{label} 超出内置渲染上限，使用过期缓存: {exc}")
            return stale_cached
        if fallback is _USE_ORIGINAL:
            logger.warning(f"{label} 超出内置渲染上限，跳过该图片: {exc}")
            return ""
        logger.warning(f"{label} 超出内置渲染上限，使用降级图片: {exc}")
        return fallback
    except Exception as exc:
        if stale_cached:
            logger.warning(f"{label} 压缩失败，使用过期缓存: {exc}")
            return stale_cached
        if fallback is _USE_ORIGINAL:
            logger.warning(f"{label} 压缩失败，使用原图: {exc}")
            return image
        logger.warning(f"{label} 压缩失败，使用降级图片: {exc}")
        return fallback


async def localize_template_avatar_images(
    templates: dict,
    cache_dir: Path | str | None,
) -> dict:
    """Replace template avatar and cover URL fields with local data URIs."""
    if not cache_dir:
        return templates
    return await _localize_avatar_value(templates, Path(cache_dir), "")


def _optimize_template_image_sync(image: Any, policy: ImageOptimizePolicy) -> str:
    raw = _load_image_bytes(image, policy)
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        resized = _resize_image(source, policy)
        return _encode_image_data_uri(resized, policy)


def _load_image_bytes(image: Any, policy: ImageOptimizePolicy) -> bytes:
    if isinstance(image, bytes):
        return image
    if not isinstance(image, str):
        raise TypeError(f"unsupported image type: {type(image)!r}")
    if image.startswith("data:image/"):
        header, _, payload = image.partition(",")
        if ";base64" not in header or not payload:
            raise ValueError("unsupported image data URI")
        return base64.b64decode(payload)
    if image.startswith(("http://", "https://")):
        request = urllib.request.Request(
            image,
            headers={
                "User-Agent": _USER_AGENT,
                "Referer": "https://www.bilibili.com/",
            },
        )
        with urllib.request.urlopen(request, timeout=_IMAGE_FETCH_TIMEOUT_SEC) as response:
            size = response.headers.get("Content-Length")
            if size and int(size) > policy.max_source_bytes:
                raise ImageTooLarge(f"source too large: {size} bytes")
            data = response.read(policy.max_source_bytes + 1)
        if len(data) > policy.max_source_bytes:
            raise ImageTooLarge(f"source too large: {len(data)} bytes")
        return data
    raise ValueError("only http(s), bytes, and image data URI are supported")


def _resize_image(source: Image.Image, policy: ImageOptimizePolicy) -> Image.Image:
    image = source.convert("RGB")
    width, height = image.size
    scale = min(
        1.0,
        policy.max_width / max(width, 1),
        policy.max_height / max(height, 1),
        (policy.max_pixels / max(width * height, 1)) ** 0.5,
    )
    if scale >= 1.0:
        return image
    target_size = (
        max(1, int(width * scale)),
        max(1, int(height * scale)),
    )
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _encode_image_data_uri(image: Image.Image, policy: ImageOptimizePolicy) -> str:
    out = io.BytesIO()
    try:
        image.save(out, format="WEBP", quality=policy.quality, method=4)
        mime = "image/webp"
    except Exception:
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=policy.quality, optimize=True)
        mime = "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


async def _localize_avatar_value(value: Any, cache_dir: Path, key_name: str) -> Any:
    if isinstance(value, dict):
        return {
            key: await _localize_avatar_value(item, cache_dir, str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [await _localize_avatar_value(item, cache_dir, "") for item in value]
    if isinstance(value, tuple):
        return tuple(
            [await _localize_avatar_value(item, cache_dir, "") for item in value]
        )
    if key_name in _AVATAR_FIELD_NAMES and isinstance(value, str):
        return await optimize_template_image(
            value,
            AVATAR_POLICY,
            label=key_name,
            fallback=DEFAULT_AVATAR_DATA_URI,
            cache_dir=cache_dir,
        )
    if key_name in _COVER_FIELD_NAMES and isinstance(value, str):
        if not value or not value.startswith(("http://", "https://")):
            return value
        return await optimize_template_image(
            value,
            DYNAMIC_HERO_POLICY,
            label=key_name,
            fallback=TRANSPARENT_IMAGE_DATA_URI,
        )
    return value


def _is_cacheable_image(image: Any) -> bool:
    return isinstance(image, str) and image.startswith(("http://", "https://"))


def _is_cacheable_result(image: Any) -> bool:
    return isinstance(image, str) and image.startswith("data:image/")


def _read_cached_image(
    cache_dir: Path,
    image: str,
    policy: ImageOptimizePolicy,
    cache_ttl_sec: int,
    cache_unused_retention_sec: int,
    allow_expired: bool,
) -> str:
    _cleanup_image_cache(cache_dir, cache_unused_retention_sec)
    data_path, meta_path = _cached_image_paths(cache_dir, image, policy)
    if not data_path.exists() or not meta_path.exists():
        return ""

    now = time.time()
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        _delete_cached_image(data_path, meta_path)
        return ""

    created_at = float(meta.get("created_at") or 0)
    if cache_ttl_sec > 0 and now - created_at > cache_ttl_sec and not allow_expired:
        return ""

    try:
        data_uri = data_path.read_text(encoding="utf-8")
    except Exception:
        _delete_cached_image(data_path, meta_path)
        return ""
    if not data_uri.startswith("data:image/"):
        _delete_cached_image(data_path, meta_path)
        return ""

    meta["last_used_at"] = now
    _write_json(meta_path, meta)
    return data_uri


def _write_cached_image(
    cache_dir: Path,
    image: str,
    policy: ImageOptimizePolicy,
    data_uri: str,
    cache_unused_retention_sec: int,
) -> None:
    _cleanup_image_cache(cache_dir, cache_unused_retention_sec)
    data_path, meta_path = _cached_image_paths(cache_dir, image, policy)
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    data_path.write_text(data_uri, encoding="utf-8")
    _write_json(
        meta_path,
        {
            "source": image,
            "created_at": now,
            "last_used_at": now,
            "policy": _policy_fingerprint(policy),
        },
    )


def _cached_image_paths(
    cache_dir: Path,
    image: str,
    policy: ImageOptimizePolicy,
) -> tuple[Path, Path]:
    key = hashlib.sha256(
        json.dumps(
            {
                "source": image,
                "policy": _policy_fingerprint(policy),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return cache_dir / f"{key}.txt", cache_dir / f"{key}.json"


def _policy_fingerprint(policy: ImageOptimizePolicy) -> dict[str, int]:
    return {
        "max_width": policy.max_width,
        "max_height": policy.max_height,
        "max_pixels": policy.max_pixels,
        "quality": policy.quality,
        "max_source_bytes": policy.max_source_bytes,
    }


def _cleanup_image_cache(cache_dir: Path, unused_retention_sec: int) -> None:
    now = time.time()
    marker = cache_dir / ".last_cleanup"
    try:
        last_cleanup = float(marker.read_text(encoding="utf-8"))
    except Exception:
        last_cleanup = 0
    if now - last_cleanup < _IMAGE_CACHE_CLEANUP_INTERVAL_SEC:
        return

    cache_dir.mkdir(parents=True, exist_ok=True)
    cutoff = now - unused_retention_sec
    for meta_path in cache_dir.glob("*.json"):
        data_path = meta_path.with_suffix(".txt")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            last_used_at = float(meta.get("last_used_at") or 0)
        except Exception:
            last_used_at = 0
        if last_used_at < cutoff:
            _delete_cached_image(data_path, meta_path)

    for data_path in cache_dir.glob("*.txt"):
        if data_path.name == ".last_cleanup":
            continue
        if not data_path.with_suffix(".json").exists():
            data_path.unlink(missing_ok=True)
    marker.write_text(str(now), encoding="utf-8")


def _delete_cached_image(data_path: Path, meta_path: Path) -> None:
    data_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
