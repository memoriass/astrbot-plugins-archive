from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlencode, urlparse

import aiohttp

from ..capability import CapabilityError
from ..credential import CredentialError, CredentialProvider


class KomgaReadOnlyAdapter:
    service_ref = "komga.production"
    capabilities = (
        "komga.list_libraries",
        "komga.search_series",
        "komga.list_recent",
    )

    def __init__(self, *, base_url: str, credential_provider: CredentialProvider, session_getter: Any, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.credential_provider = credential_provider
        self.session_getter = session_getter
        self.timeout_seconds = max(1, min(int(timeout_seconds or 10), 60))

    async def list_libraries(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if arguments:
            raise CapabilityError("komga_arguments_not_allowed")
        items = _content(await self._get("/api/v1/libraries", credential_ref))
        return {"ok": True, "read_only": True, "libraries": [_safe(item) for item in items], "count": len(items)}

    async def search_series(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if set(arguments) - {"query", "limit"}:
            raise CapabilityError("komga_arguments_not_allowed")
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise CapabilityError("komga_query_missing")
        limit = _limit(arguments.get("limit"), 20)
        path = "/api/v1/series?" + urlencode({"search": query, "size": limit})
        items = _content(await self._get(path, credential_ref))
        return {"ok": True, "read_only": True, "series": [_series(item) for item in items], "count": len(items)}

    async def list_recent(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if set(arguments) - {"limit"}:
            raise CapabilityError("komga_arguments_not_allowed")
        limit = _limit(arguments.get("limit"), 20)
        path = "/api/v1/books?" + urlencode({"sort": "fileLastModified,desc", "size": limit})
        items = _content(await self._get(path, credential_ref))
        return {"ok": True, "read_only": True, "books": [_book(item) for item in items], "count": len(items)}

    async def _get(self, path: str, credential_ref: str) -> Any:
        if not _private_url(self.base_url):
            raise CapabilityError("komga_url_not_private")
        session = self.session_getter()
        if session is None:
            raise CapabilityError("http_session_unavailable")
        try:
            credential = self.credential_provider.get(credential_ref or "komga.production.readonly")
        except CredentialError as exc:
            raise CapabilityError(str(exc)) from exc
        headers = {"Accept": "application/json"}
        auth = None
        api_key = str(credential.get("api_key") or "")
        if api_key:
            headers["X-API-Key"] = api_key
        else:
            username = str(credential.get("username") or "")
            password = str(credential.get("password") or "")
            if not username or not password:
                raise CapabilityError("komga_credential_missing")
            auth = aiohttp.BasicAuth(username, password)
        try:
            async with session.get(
                self.base_url + path,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise CapabilityError(f"komga_http_{response.status}")
                return data
        except aiohttp.ClientError as exc:
            raise CapabilityError("komga_request_failed") from exc


def _content(data: Any) -> list[dict[str, Any]]:
    value = data if isinstance(data, list) else data.get("content", []) if isinstance(data, dict) else []
    return [item for item in value if isinstance(item, dict)]


def _safe(item: dict[str, Any]) -> dict[str, Any]:
    return {str(key)[:80]: value for key, value in item.items() if isinstance(value, (str, int, float, bool, type(None)))}


def _series(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {"id": str(item.get("id") or "")[:120], "name": str(metadata.get("title") or item.get("name") or "")[:300], "books_count": int(item.get("booksCount") or 0)}


def _book(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {"id": str(item.get("id") or "")[:120], "series_id": str(item.get("seriesId") or "")[:120], "name": str(metadata.get("title") or item.get("name") or "")[:300]}


def _limit(value: Any, default: int) -> int:
    try:
        return max(1, min(int(value or default), 100))
    except (TypeError, ValueError) as exc:
        raise CapabilityError("komga_limit_invalid") from exc


def _private_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        host = ip_address(parsed.hostname)
    except ValueError:
        return parsed.hostname == "localhost"
    return host.is_private or host.is_loopback
