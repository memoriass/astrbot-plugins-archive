from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlencode, urlparse

import aiohttp

from ..capability import CapabilityError


class QBittorrentReadOnlyAdapter:
    service_ref = "qbittorrent.production"
    list_capability = "qbittorrent.list_torrents"
    transfer_capability = "qbittorrent.transfer_status"

    def __init__(self, *, base_url: str, session_getter: Any, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_getter = session_getter
        self.timeout_seconds = max(1, min(int(timeout_seconds or 10), 60))

    async def list_torrents(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if credential_ref or set(arguments) - {"filter", "category", "limit"}:
            raise CapabilityError("qbittorrent_arguments_not_allowed")
        query: dict[str, str] = {}
        torrent_filter = str(arguments.get("filter") or "").strip()
        category = str(arguments.get("category") or "").strip()
        if torrent_filter:
            query["filter"] = torrent_filter[:32]
        if category:
            query["category"] = category[:100]
        try:
            limit = max(1, min(int(arguments.get("limit", 50) or 50), 100))
        except (TypeError, ValueError) as exc:
            raise CapabilityError("qbittorrent_limit_invalid") from exc
        data = await self._get_json("/api/v2/torrents/info", query)
        if not isinstance(data, list):
            raise CapabilityError("qbittorrent_response_invalid")
        total = len(data)
        visible = [_project_torrent(item) for item in data[:limit] if isinstance(item, dict)]
        active = sum(item["state"] not in {"pausedDL", "pausedUP", "stoppedDL", "stoppedUP", "error"} for item in visible)
        return {
            "ok": True,
            "capability": self.list_capability,
            "read_only": True,
            "torrents": visible,
            "count": total,
            "returned_count": len(visible),
            "result_summary": f"qBittorrent torrents: {total}; active in result: {active}",
        }

    async def transfer_status(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if credential_ref or arguments:
            raise CapabilityError("qbittorrent_arguments_not_allowed")
        data = await self._get_json("/api/v2/transfer/info", {})
        if not isinstance(data, dict):
            raise CapabilityError("qbittorrent_response_invalid")
        status = {
            "connection_status": str(data.get("connection_status") or "")[:32],
            "download_speed": int(data.get("dl_info_speed") or 0),
            "upload_speed": int(data.get("up_info_speed") or 0),
            "downloaded": int(data.get("dl_info_data") or 0),
            "uploaded": int(data.get("up_info_data") or 0),
            "dht_nodes": int(data.get("dht_nodes") or 0),
        }
        return {
            "ok": True,
            "capability": self.transfer_capability,
            "read_only": True,
            "transfer": status,
            "result_summary": f"qBittorrent: {status['connection_status']}; down {status['download_speed']} B/s; up {status['upload_speed']} B/s",
        }

    async def _get_json(self, path: str, query: dict[str, str]) -> Any:
        if not _is_private_url(self.base_url):
            raise CapabilityError("qbittorrent_url_not_private")
        session = self.session_getter()
        if session is None:
            raise CapabilityError("http_session_unavailable")
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urlencode(query)
        try:
            async with session.get(
                url,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                if response.status in {401, 403}:
                    raise CapabilityError("qbittorrent_auth_required")
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise CapabilityError(f"qbittorrent_http_{response.status}")
                return data
        except aiohttp.ClientError as exc:
            raise CapabilityError("qbittorrent_request_failed") from exc


def _project_torrent(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "hash": str(item.get("hash") or "")[:40],
        "name": str(item.get("name") or "")[:300],
        "state": str(item.get("state") or "")[:32],
        "progress": round(float(item.get("progress") or 0), 4),
        "size": int(item.get("size") or 0),
        "download_speed": int(item.get("dlspeed") or 0),
        "upload_speed": int(item.get("upspeed") or 0),
        "eta": int(item.get("eta") or 0),
        "category": str(item.get("category") or "")[:100],
    }


def _is_private_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname.lower() == "localhost":
        return True
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(address.is_loopback or address.is_private)
