from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable

from .http import HttpClient
from .network_retry import get_with_retry

try:
    from ..utils.image_optimizer import DEFAULT_AVATAR_DATA_URI
    from ..utils.logger import logger
except ImportError:
    from utils.image_optimizer import DEFAULT_AVATAR_DATA_URI
    from utils.logger import logger


NO_FACE = DEFAULT_AVATAR_DATA_URI
KV_KEY = "bili_avatar_cache"
REFRESH_AFTER_SEC = 24 * 3600
UNUSED_RETENTION_SEC = 120 * 24 * 3600
FETCH_CONCURRENCY = 4


_cache: dict[str, dict] = {}
_loaded = False
_lock = asyncio.Lock()
_fetch_semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)


async def fetch_avatar_map(star, uids: Iterable[str]) -> dict[str, str]:
    """Return UID -> face URL with a persistent KV cache and bounded fetch queue."""
    uid_list = _normalize_uids(uids)
    if not uid_list:
        return {}

    if star is None:
        fetched = await _fetch_uncached(uid_list)
        return {uid: fetched.get(uid) or NO_FACE for uid in uid_list}

    now = time.time()
    await _ensure_loaded(star)
    result: dict[str, str] = {}
    stale: list[str] = []

    async with _lock:
        for uid in uid_list:
            entry = _cache_entry(uid)
            face = str(entry.get("face") or "")
            fetched_at = float(entry.get("fetched_at") or 0)
            if face and now - fetched_at <= REFRESH_AFTER_SEC:
                entry["last_used_at"] = now
                _cache[uid] = entry
                result[uid] = face
            else:
                stale.append(uid)

    if stale:
        fetched = await _fetch_uncached(stale)
        async with _lock:
            for uid in stale:
                entry = _cache_entry(uid)
                face = fetched.get(uid) or str(entry.get("face") or NO_FACE)
                result[uid] = face
                _cache[uid] = {
                    "face": face,
                    "fetched_at": (
                        now
                        if fetched.get(uid)
                        else float(entry.get("fetched_at") or 0)
                    ),
                    "last_used_at": now,
                }

    await _cleanup_and_save(star)
    return {uid: result.get(uid, NO_FACE) for uid in uid_list}


async def _ensure_loaded(star) -> None:
    global _loaded, _cache
    if _loaded:
        return
    async with _lock:
        if _loaded:
            return
        try:
            data = await star.get_kv_data(KV_KEY, {})
            _cache = data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning(f"头像缓存加载失败，将使用空缓存: {exc}")
            _cache = {}
        _loaded = True


async def _cleanup_and_save(star) -> None:
    now = time.time()
    subscribed_uids = _subscription_uids(star)
    async with _lock:
        expired = [
            uid
            for uid, entry in _cache.items()
            if uid not in subscribed_uids
            and now - _entry_last_used_at(entry) > UNUSED_RETENTION_SEC
        ]
        for uid in expired:
            _cache.pop(uid, None)
        snapshot = dict(_cache)
    try:
        await star.put_kv_data(KV_KEY, snapshot)
    except Exception as exc:
        logger.warning(f"头像缓存保存失败: {exc}")


async def _fetch_uncached(uids: list[str]) -> dict[str, str]:
    client = await HttpClient.get_client()

    async def fetch(uid: str) -> tuple[str, str]:
        async with _fetch_semaphore:
            face = ""
            try:
                res = await get_with_retry(
                    client,
                    "https://api.bilibili.com/x/web-interface/card",
                    label=f"获取头像 {uid}",
                    params={"mid": uid},
                    timeout=5,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("code") == 0:
                        face = (
                            data.get("data", {}).get("card", {}).get("face")
                            or NO_FACE
                        )
            except Exception as exc:
                logger.debug(f"获取头像失败 {uid}: {exc}")
                return uid, ""
            return uid, face

    return dict(await asyncio.gather(*[fetch(uid) for uid in uids]))


def _normalize_uids(uids: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for uid in uids:
        value = str(uid or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _cache_entry(uid: str) -> dict:
    entry = _cache.get(uid)
    return entry if isinstance(entry, dict) else {}


def _entry_last_used_at(entry) -> float:
    if not isinstance(entry, dict):
        return 0.0
    return float(entry.get("last_used_at") or 0)


def _subscription_uids(star) -> set[str]:
    db = getattr(star, "db", None)
    if db is None:
        return set()
    try:
        return {
            str(sub.uid)
            for sub in db.get_subscriptions()
            if getattr(sub, "uid", "")
        }
    except Exception:
        return set()
