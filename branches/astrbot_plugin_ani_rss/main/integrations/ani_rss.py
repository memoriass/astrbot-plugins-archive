from __future__ import annotations

import json
from typing import Any

import aiohttp


class AniRssError(Exception):
    pass


class AniRssClient:
    def __init__(
        self,
        base_url: str,
        api_prefix: str,
        api_key: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        prefix = api_prefix.strip()
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        self.api_prefix = prefix.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = aiohttp.ClientTimeout(total=max(timeout_seconds, 1))

    def _url(self, path: str) -> str:
        clean_path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{self.api_prefix}{clean_path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path)
        headers = self._headers()
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=payload,
                    params=params,
                ) as response:
                    text = await response.text()
                    data = self._decode_json(text, url)
                    if response.status >= 400:
                        message = data.get("message") or response.reason
                        raise AniRssError(f"HTTP {response.status}: {message}")
                    code = data.get("code")
                    if isinstance(code, int) and not 200 <= code < 300:
                        raise AniRssError(data.get("message") or f"ANI-RSS code {code}")
                    return data
        except TimeoutError as exc:
            raise AniRssError(f"Request timed out: {url}") from exc
        except aiohttp.ClientError as exc:
            raise AniRssError(f"Request failed: {exc}") from exc

    async def request_first(
        self,
        candidates: list[tuple[str, str, Any | None, dict[str, Any] | None]],
    ) -> dict[str, Any]:
        errors: list[str] = []
        for method, path, payload, params in candidates:
            try:
                return await self.request(method, path, payload=payload, params=params)
            except AniRssError as exc:
                errors.append(f"{method} {path}: {exc}")
        raise AniRssError("; ".join(errors))

    @staticmethod
    def _decode_json(text: str, url: str) -> dict[str, Any]:
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise AniRssError(f"Non-JSON response from {url}: {text[:200]}") from exc
        if not isinstance(data, dict):
            raise AniRssError(f"Unexpected response from {url}: {type(data).__name__}")
        return data

    async def ping(self) -> dict[str, Any]:
        return await self.request_first(
            [
                ("GET", "/ping", None, None),
                ("POST", "/ping", {}, None),
                ("GET", "/test", None, None),
                ("POST", "/test", {}, None),
            ],
        )

    async def about(self) -> dict[str, Any]:
        return await self.request_first(
            [
                ("POST", "/about", {}, None),
                ("GET", "/about", None, None),
            ],
        )

    async def rss_to_ani(
        self,
        *,
        rss_url: str,
        rss_type: str,
        bgm_url: str = "",
        subgroup: str = "",
        enable: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "url": rss_url.strip(),
            "type": rss_type,
            "season": 1,
            "offset": 0,
            "title": "",
            "exclude": [],
            "totalEpisodeNumber": 0,
            "match": [],
            "enable": enable,
        }
        if bgm_url:
            payload["bgmUrl"] = bgm_url.strip()
        if subgroup:
            payload["subgroup"] = subgroup.strip()
        result = await self.request_first(
            [
                ("POST", "/rssToAni", payload, None),
                ("POST", "/rss", payload, None),
            ],
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise AniRssError(result.get("message") or "rss returned no data")
        return data

    async def add_ani(self, ani: dict[str, Any]) -> str:
        result = await self.request_first(
            [
                ("POST", "/addAni", ani, None),
                ("POST", "/ani", ani, None),
            ],
        )
        return str(result.get("message") or "Subscription added")

    async def delete_ani(self, subscription_ids: list[str], *, delete_files: bool = False) -> str:
        ids = [str(item).strip() for item in subscription_ids if str(item).strip()]
        if not ids:
            raise AniRssError("subscription_ids are required.")
        result = await self.request(
            "POST",
            "/deleteAni",
            payload=ids,
            params={"deleteFiles": str(bool(delete_files)).lower()},
        )
        return str(result.get("message") or "Subscription deleted")

    async def preview_ani(self, ani: dict[str, Any]) -> dict[str, Any]:
        result = await self.request_first(
            [
                ("POST", "/previewAni", ani, None),
                ("POST", "/items", ani, None),
            ],
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise AniRssError(result.get("message") or "items returned no data")
        return data

    async def list_ani(self) -> list[dict[str, Any]]:
        result = await self.request_first(
            [
                ("POST", "/listAni", {}, None),
                ("GET", "/ani", None, None),
            ],
        )
        data = result.get("data") or {}
        return flatten_ani_list(data)

    async def refresh_all(self) -> str:
        result = await self.request_first(
            [
                ("POST", "/refreshAll", {}, None),
                ("POST", "/ani", None, {"type": "download"}),
            ],
        )
        return str(result.get("message") or "Refresh started")

    async def refresh_ani(self, subscription_id: str) -> str:
        target_id = subscription_id.strip()
        if not target_id:
            raise AniRssError("subscription_id is required.")
        try:
            result = await self.request("POST", "/refreshAni", payload={"id": target_id})
            return str(result.get("message") or "Refresh started")
        except AniRssError:
            pass
        target = next(
            (ani for ani in await self.list_ani() if str(ani.get("id") or "") == target_id),
            None,
        )
        if target is None:
            raise AniRssError(f"Subscription not found: {target_id}")
        result = await self.request("POST", "/ani", payload=target, params={"type": "download"})
        return str(result.get("message") or "Refresh started")

    async def mikan_search(
        self,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = await self.request(
            "POST",
            "/mikan",
            payload=payload or {},
            params={"text": text.strip()},
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise AniRssError(result.get("message") or "mikan returned no data")
        return data

    async def mikan_groups(self, url: str) -> list[dict[str, Any]]:
        result = await self.request_first(
            [
                ("POST", "/mikanGroup", {}, {"url": url.strip()}),
                ("GET", "/mikan/group", None, {"url": url.strip()}),
                ("POST", "/mikan/group", {}, {"url": url.strip()}),
            ],
        )
        data = result.get("data")
        if not isinstance(data, list):
            raise AniRssError(result.get("message") or "mikan group returned no data")
        return [item for item in data if isinstance(item, dict)]

def flatten_ani_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for week in data.get("weekList") or []:
        if not isinstance(week, dict):
            continue
        for ani in week.get("items") or []:
            if not isinstance(ani, dict):
                continue
            ani_id = str(ani.get("id") or "")
            if ani_id and ani_id in seen_ids:
                continue
            if ani_id:
                seen_ids.add(ani_id)
            items.append(ani)
    return items
