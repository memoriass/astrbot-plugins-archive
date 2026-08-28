"""HTTP 客户端封装"""

import time
from typing import TYPE_CHECKING, Optional

import httpx

from .config import PluginConfig, load_plugin_config

if TYPE_CHECKING:
    from astrbot.api.star import Star


class HttpClient:
    _client: httpx.AsyncClient | None = None
    _buvid_initialized: bool = False
    _star_instance: Optional["Star"] = None
    _verify_ssl: bool = True
    _risk_cooldown_sec: int = 1800

    # Account Pool
    # Structure: [{"uid": str, "name": str, "face": str, "cookies": dict, "valid": bool}]
    _accounts: list[dict] = []
    _current_account_index: int = 0

    @classmethod
    async def set_star_instance(cls, star: "Star"):
        cls._star_instance = star

        conf = {}
        context = getattr(star, "context", None)
        if context is not None:
            get_config = getattr(context, "get_config", None)
            if callable(get_config):
                try:
                    conf = get_config() or {}
                except Exception:
                    conf = {}

        if not conf:
            conf = getattr(star, "config", {}) or {}

        parsed_config = (
            conf if isinstance(conf, PluginConfig) else load_plugin_config(conf)
        )
        cls._verify_ssl = parsed_config.verify_ssl
        cls._risk_cooldown_sec = parsed_config.risk_cooldown_sec
        await cls.load_accounts()

    @classmethod
    async def load_accounts(cls):
        if cls._star_instance:
            db = cls._account_db()
            cls._accounts = db.get_accounts() if db else []
            cls._current_account_index = 0
            await cls._refresh_account_states()

    @classmethod
    async def save_accounts(cls):
        db = cls._account_db()
        if db:
            for account in cls._accounts:
                db.upsert_account(account)

    @classmethod
    async def add_account(cls, uid: str, name: str, face: str, cookies: dict):
        # Update if exists
        for acc in cls._accounts:
            if str(acc.get("uid")) == str(uid):
                acc["name"] = name
                acc["face"] = face
                acc["cookies"] = cookies
                acc["valid"] = True
                cls._clear_transient_status(acc)
                await cls.save_accounts()
                await cls.close()
                return

        # Add new
        cls._accounts.append(
            {
                "uid": str(uid),
                "name": name,
                "face": face,
                "cookies": cookies,
                "valid": True,
            }
        )
        await cls.save_accounts()
        await cls.close()

    @classmethod
    async def upsert_account(
        cls,
        uid: str,
        name: str,
        face: str,
        cookies: dict | None = None,
        valid: bool = True,
    ):
        for acc in cls._accounts:
            if str(acc.get("uid")) == str(uid):
                acc["name"] = name
                acc["face"] = face
                acc["valid"] = valid
                if cookies is not None:
                    acc["cookies"] = cookies
                if valid:
                    cls._clear_transient_status(acc)
                await cls.save_accounts()
                await cls.close()
                return

        cls._accounts.append(
            {
                "uid": str(uid),
                "name": name,
                "face": face,
                "cookies": cookies or {},
                "valid": valid,
            }
        )
        await cls.save_accounts()
        await cls.close()

    @classmethod
    async def remove_account(cls, uid: str) -> bool:
        uid = str(uid)
        before = len(cls._accounts)
        cls._accounts = [acc for acc in cls._accounts if str(acc.get("uid")) != uid]
        if len(cls._accounts) == before:
            return False
        db = cls._account_db()
        if db:
            db.remove_account(uid)
        cls._current_account_index = min(
            cls._current_account_index,
            max(len(cls._accounts) - 1, 0),
        )
        await cls.save_accounts()
        await cls.close()
        return True

    @classmethod
    async def set_account_valid(cls, uid: str, valid: bool) -> bool:
        for acc in cls._accounts:
            if str(acc.get("uid")) == str(uid):
                acc["valid"] = valid
                cls._clear_transient_status(acc)
                db = cls._account_db()
                if db:
                    db.set_account_valid(uid, valid)
                else:
                    await cls.save_accounts()
                await cls.close()
                return True
        return False

    @classmethod
    async def get_accounts(cls) -> list[dict]:
        if not cls._accounts and cls._star_instance:
            await cls.load_accounts()
        await cls._refresh_account_states()
        return cls._accounts

    @classmethod
    async def rotate_account(cls) -> bool:
        """Switch to next valid account. Returns True if successful, False if no valid accounts."""
        attempts = 0
        total = len(cls._accounts)
        if total == 0:
            return False
        await cls._refresh_account_states()

        while attempts < total:
            cls._current_account_index = (cls._current_account_index + 1) % total
            acc = cls._accounts[cls._current_account_index]
            if cls._is_account_available(acc):
                if cls._client:
                    cls._client.cookies.clear()
                    cls._client.cookies.update(acc["cookies"])
                from ..utils.logger import logger

                logger.info(
                    f"Switched to Bilibili account: {acc.get('name')} (UID: {acc.get('uid')})"
                )
                return True
            attempts += 1

        return False

    @classmethod
    async def set_current_account_status(
        cls, valid: bool = True, status_code: int = None
    ):
        if not cls._accounts:
            return
        acc = cls._accounts[cls._current_account_index]
        acc["valid"] = valid
        if valid and status_code is None:
            cls._clear_transient_status(acc)
        else:
            acc["status_code"] = status_code
        await cls.save_accounts()

    @classmethod
    async def invalidate_current_account(cls, status_code: int = None) -> bool:
        if not cls._accounts:
            return False
        acc = cls._accounts[cls._current_account_index]
        acc["valid"] = True
        acc["status_code"] = status_code
        acc["cooldown_until"] = int(time.time() + cls._risk_cooldown_sec)
        acc["failure_count"] = int(acc.get("failure_count") or 0) + 1
        from ..utils.logger import logger

        logger.warning(
            f"Cooling down account (Code {status_code}): {acc.get('name')} "
            f"(UID: {acc.get('uid')}) for {cls._risk_cooldown_sec}s"
        )
        await cls.save_accounts()
        return await cls.rotate_account()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com/",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                timeout=20.0,
                follow_redirects=True,
                cookies={},
                verify=cls._verify_ssl,
            )
            cls._buvid_initialized = False

            # Load accounts if not loaded
            if not cls._accounts:
                await cls.load_accounts()
            await cls._refresh_account_states()

            # Apply current account cookies
            if cls._accounts:
                acc = cls._accounts[cls._current_account_index]
                if not cls._is_account_available(acc):
                    # Try to find a valid one
                    rotated = await cls.rotate_account()
                    if not rotated:
                        cls._client.cookies.clear()
                        return cls._client
                    acc = cls._accounts[cls._current_account_index]

                if cls._is_account_available(acc):
                    cls._client.cookies.update(acc["cookies"])
                    cls._buvid_initialized = True

        if not cls._buvid_initialized:
            try:
                await cls._client.get("https://www.bilibili.com/", timeout=5.0)
                await cls._client.get(
                    "https://api.bilibili.com/x/frontend/finger/spi", timeout=5.0
                )
                cls._buvid_initialized = True
            except Exception as e:
                from ..utils.logger import logger

                logger.warning(f"初始化 B站 Cookies 失败: {e}")

        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.aclose()
            cls._client = None

    @classmethod
    def _is_account_available(cls, account: dict) -> bool:
        if not account.get("valid", True):
            return False
        return int(account.get("cooldown_until") or 0) <= int(time.time())

    @classmethod
    async def _refresh_account_states(cls):
        changed = False
        now = int(time.time())
        for acc in cls._accounts:
            cooldown_until = int(acc.get("cooldown_until") or 0)
            if cooldown_until and cooldown_until <= now:
                cls._clear_transient_status(acc)
                changed = True
        if changed:
            await cls.save_accounts()

    @staticmethod
    def _clear_transient_status(account: dict):
        account.pop("status_code", None)
        account.pop("cooldown_until", None)
        account.pop("failure_count", None)

    @classmethod
    def _account_db(cls):
        return getattr(cls._star_instance, "db", None)
