from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import aiohttp


class KomgaError(RuntimeError):
    pass


class KomgaClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.base_url = _validated_base_url(
            str(config.get("base_url") or "http://127.0.0.1:25600"),
            allow_public=bool(config.get("allow_public_url", False)),
        )
        self.api_key = str(config.get("api_key") or "").strip()
        self.username = str(config.get("username") or "").strip()
        self.password = str(config.get("password") or "")
        self.timeout_seconds = max(1, min(int(config.get("timeout_seconds") or 15), 60))
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def list_libraries(self) -> list[dict[str, Any]]:
        return [_library(item) for item in _content(await self._get("/api/v1/libraries"))]

    async def list_recent(self, limit: int) -> list[dict[str, Any]]:
        data = await self._get(
            "/api/v1/books",
            {"sort": "fileLastModified,desc", "size": _limit(limit)},
        )
        return [_book(item) for item in _content(data)]

    async def search_series(self, query: str, limit: int) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            raise KomgaError("series query is required")
        data = await self._get("/api/v1/series", {"search": query, "size": _limit(limit)})
        return [_series(item) for item in _content(data)]

    async def series_detail(self, series_id: str) -> dict[str, Any]:
        series_id = _identifier(series_id, "series_id")
        data = await self._get(f"/api/v1/series/{series_id}")
        if not isinstance(data, dict):
            raise KomgaError("invalid series detail response")
        return _series_detail(data)

    async def list_books(self, series_id: str, limit: int) -> list[dict[str, Any]]:
        series_id = _identifier(series_id, "series_id")
        data = await self._get(
            f"/api/v1/series/{series_id}/books",
            {"size": _limit(limit), "sort": "metadata.numberSort,asc"},
        )
        return [_book(item) for item in _content(data)]

    async def on_deck(self, limit: int) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/books/ondeck", {"size": _limit(limit)})
        return [_book(item) for item in _content(data)]

    async def collections(self, limit: int) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/collections", {"size": _limit(limit)})
        return [_named_item(item) for item in _content(data)]

    async def readlists(self, limit: int) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/readlists", {"size": _limit(limit)})
        return [_named_item(item) for item in _content(data)]

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        session = self._session
        if session is None or session.closed:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds))
            self._session = session
        headers = {"Accept": "application/json"}
        auth = None
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.username and self.password:
            auth = aiohttp.BasicAuth(self.username, self.password)
        else:
            raise KomgaError("Komga credential is missing")
        try:
            async with session.get(
                self.base_url + path,
                params=params,
                headers=headers,
                auth=auth,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise KomgaError(f"Komga HTTP {response.status}")
                return data
        except KomgaError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise KomgaError("Komga request failed") from exc


def _validated_base_url(value: str, *, allow_public: bool) -> str:
    text = str(value or "").strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise KomgaError("Komga base_url must be an http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise KomgaError("Komga base_url must not contain credentials, query, or fragment")
    if not allow_public and not _private_host(parsed.hostname):
        raise KomgaError("Komga base_url must be private unless allow_public_url is enabled")
    return text


def _private_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        address = ip_address(hostname)
    except ValueError:
        return False
    return address.is_private or address.is_loopback


def _content(data: Any) -> list[dict[str, Any]]:
    value = data if isinstance(data, list) else data.get("content", []) if isinstance(data, dict) else []
    return [item for item in value if isinstance(item, dict)]


def _library(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(item.get("id"), 120),
        "name": _text(item.get("name"), 300),
        "root": _text(item.get("root"), 500),
        "scan_interval": _text(item.get("scanInterval"), 80),
    }


def _series(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {
        "id": _text(item.get("id"), 120),
        "library_id": _text(item.get("libraryId"), 120),
        "name": _text(metadata.get("title") or item.get("name"), 300),
        "books_count": _integer(item.get("booksCount")),
        "books_read_count": _integer(item.get("booksReadCount")),
        "books_unread_count": _integer(item.get("booksUnreadCount")),
        "status": _text(metadata.get("status"), 80),
    }


def _series_detail(item: dict[str, Any]) -> dict[str, Any]:
    result = _series(item)
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    result.update(
        {
            "summary": _text(metadata.get("summary"), 2000),
            "publisher": _text(metadata.get("publisher"), 300),
            "genres": _text_list(metadata.get("genres"), 30),
            "tags": _text_list(metadata.get("tags"), 30),
        },
    )
    return result


def _book(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    media = item.get("media") if isinstance(item.get("media"), dict) else {}
    return {
        "id": _text(item.get("id"), 120),
        "series_id": _text(item.get("seriesId"), 120),
        "name": _text(metadata.get("title") or item.get("name"), 300),
        "number": _text(metadata.get("number"), 80),
        "pages_count": _integer(media.get("pagesCount")),
        "read_progress": _integer(item.get("readProgress", {}).get("page") if isinstance(item.get("readProgress"), dict) else 0),
    }


def _named_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(item.get("id"), 120),
        "name": _text(item.get("name"), 300),
        "ordered": bool(item.get("ordered", False)),
        "book_ids": _text_list(item.get("bookIds"), 100),
        "series_ids": _text_list(item.get("seriesIds"), 100),
    }


def _identifier(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 120 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in text):
        raise KomgaError(f"invalid {name}")
    return text


def _limit(value: Any) -> int:
    try:
        return max(1, min(int(value or 20), 100))
    except (TypeError, ValueError) as exc:
        raise KomgaError("invalid limit") from exc


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _text_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, 300) for item in value[:limit] if isinstance(item, (str, int, float))]

