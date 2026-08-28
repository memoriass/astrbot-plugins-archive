import json
from dataclasses import dataclass
from typing import Any

import aiohttp
from astrbot.api import logger


@dataclass(frozen=True, slots=True)
class ManagerProfile:
    id: str
    name: str
    manager_url: str
    api_key: str

    def as_client_config(self) -> dict[str, str]:
        return {
            "manager_id": self.id,
            "manager_name": self.name,
            "manager_url": self.manager_url,
            "api_key": self.api_key,
        }


def _clean_manager_id(value: object, default: str = "default") -> str:
    text = str(value or "").strip().lower()
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    return text.strip("-_") or default


def _parse_manager_profiles(config: dict[str, Any]) -> tuple[list[ManagerProfile], str]:
    raw = config.get("manager_profiles")
    profiles: list[ManagerProfile] = []

    if isinstance(raw, list):
        items = [item for item in raw if isinstance(item, dict)]
    else:
        if raw:
            logger.warning(
                "manager_profiles 应为 AstrBot template_list 列表，请在插件配置页重新保存。"
            )
        items = []

    default_id = _clean_manager_id(config.get("default_manager"), default="local")
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        url = str(item.get("manager_url") or item.get("url") or "").strip().rstrip("/")
        api_key = str(item.get("api_key") or item.get("key") or "").strip()
        name = str(item.get("name") or item.get("display_name") or "").strip()
        if not any((str(item.get("id") or "").strip(), name, url, api_key)):
            continue
        manager_id = _clean_manager_id(item.get("id"), default=f"manager-{index}")
        if manager_id in seen:
            logger.warning("重复的 ncqq-manager 面板 ID 已跳过：%s", manager_id)
            continue
        seen.add(manager_id)
        name = name or manager_id
        profiles.append(ManagerProfile(manager_id, name, url, api_key))

    if not profiles:
        profiles.append(ManagerProfile(default_id, default_id, "", ""))

    if default_id not in {item.id for item in profiles}:
        default_id = profiles[0].id
    return profiles, default_id


class NCQQClient:
    """HTTP client for ncqq-manager API.

    持有一个长期复用的 ``aiohttp.ClientSession``，避免每次请求都创建/销毁
    TCP 连接。插件卸载/重载时需调用 :meth:`close` 释放资源。
    """

    def __init__(self, config: dict):
        self.config = config
        self._session: aiohttp.ClientSession | None = None

    # -- session lifecycle --------------------------------------------------

    def _build_session(self) -> aiohttp.ClientSession:
        api_key = self.config.get("api_key", "")
        return aiohttp.ClientSession(
            headers={"x-request-api-key": api_key},
            timeout=aiohttp.ClientTimeout(total=15),
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = self._build_session()
        return self._session

    async def close(self) -> None:
        """关闭底层 HTTP 会话。由插件 terminate() 调用。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- request ------------------------------------------------------------

    async def make_request(self, method: str, endpoint: str, **kwargs):
        base_url = self.config.get("manager_url", "")
        if base_url:
            base_url = base_url.rstrip("/")
        api_key = self.config.get("api_key", "")

        if not base_url or not api_key:
            raise Exception(
                "Manager URL 或 API Key 未配置，请在 AstrBot 控制台设置面板中完成配置。"
            )

        session = await self._get_session()
        url = f"{base_url}{endpoint}"

        async with session.request(method, url, **kwargs) as resp:
            if resp.status >= 400:
                text_content = await resp.text()
                logger.warning("API %s %s → %s: %s", method, endpoint, resp.status, text_content)
                raise Exception(f"请求失败（HTTP {resp.status}），请稍后重试或联系管理员。")
            return await resp.json()

    async def stream_events(self, instance_name: str, timeout: int = 60) -> list[dict]:
        """短时订阅单实例 SSE 事件流。"""
        base_url = self.config.get("manager_url", "")
        if base_url:
            base_url = base_url.rstrip("/")
        api_key = self.config.get("api_key", "")

        if not base_url or not api_key:
            raise Exception(
                "Manager URL 或 API Key 未配置，请在 AstrBot 控制台设置面板中完成配置。"
            )

        session = await self._get_session()
        url = f"{base_url}/api/containers/{instance_name}/events"
        started = False
        events: list[dict] = []
        stream_timeout = aiohttp.ClientTimeout(total=None, sock_read=timeout + 5)

        async with session.get(
            url,
            headers={"Accept": "text/event-stream"},
            timeout=stream_timeout,
        ) as resp:
            if resp.status >= 400:
                text_content = await resp.text()
                logger.warning(
                    "SSE %s → %s: %s", url, resp.status, text_content
                )
                raise Exception(f"SSE 请求失败（HTTP {resp.status}）。")

            buffer: list[str] = []
            loop = aiohttp.helpers.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    raw = await resp.content.readline()
                except Exception as e:
                    logger.warning("SSE 读取异常 %s: %s", instance_name, e)
                    break
                if raw == b"":
                    break
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    payload = self._parse_sse_payload(buffer)
                    buffer.clear()
                    if payload:
                        events.append(payload)
                        started = True
                    continue
                if line.startswith(":"):
                    continue
                buffer.append(line)
                if started and len(events) >= 8:
                    break

            payload = self._parse_sse_payload(buffer)
            if payload:
                events.append(payload)
        return events

    @staticmethod
    def _parse_sse_payload(lines: list[str]) -> dict | None:
        if not lines:
            return None
        data_lines: list[str] = []
        event_name = "message"
        for line in lines:
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if not data_lines:
            return None
        raw = "\n".join(data_lines)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("SSE payload 解析失败: %s", raw)
            return None
        if isinstance(payload, dict):
            payload.setdefault("event", event_name)
            return payload
        return {"event": event_name, "data": payload}


class NCQQClientRegistry:
    def __init__(self, config: dict[str, Any]):
        profiles, default_id = _parse_manager_profiles(config)
        self.profiles: dict[str, ManagerProfile] = {item.id: item for item in profiles}
        self.default_id = default_id
        self._clients: dict[str, NCQQClient] = {}

    def normalize_id(self, manager_id: object = "") -> str:
        cleaned = _clean_manager_id(manager_id, default=self.default_id)
        if cleaned not in self.profiles:
            raise KeyError(cleaned)
        return cleaned

    def get(self, manager_id: object = "") -> NCQQClient:
        normalized = self.normalize_id(manager_id)
        client = self._clients.get(normalized)
        if client is None:
            client = NCQQClient(self.profiles[normalized].as_client_config())
            self._clients[normalized] = client
        return client

    def profile(self, manager_id: object = "") -> ManagerProfile:
        return self.profiles[self.normalize_id(manager_id)]

    def ids(self) -> list[str]:
        return list(self.profiles)

    def labels(self) -> list[str]:
        return [f"{item.id}({item.name})" for item in self.profiles.values()]

    async def close(self) -> None:
        for client in list(self._clients.values()):
            await client.close()
        self._clients.clear()
