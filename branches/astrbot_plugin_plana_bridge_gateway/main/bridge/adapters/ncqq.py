from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import aiohttp

from ..capability import CapabilityError


class NcqqReadOnlyAdapter:
    service_ref = "ncqq.production"
    list_capability = "ncqq.list_instances"
    status_capability = "ncqq.get_login_status"

    def __init__(self, *, base_url: str, session_getter: Any, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_getter = session_getter
        self.timeout_seconds = max(1, min(int(timeout_seconds or 10), 60))

    async def list_instances(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if credential_ref or set(arguments) - {"status", "keyword", "limit"}:
            raise CapabilityError("ncqq_arguments_not_allowed")
        status = str(arguments.get("status") or "").strip().lower()
        keyword = str(arguments.get("keyword") or "").strip().casefold()
        try:
            limit = max(1, min(int(arguments.get("limit", 50) or 50), 100))
        except (TypeError, ValueError) as exc:
            raise CapabilityError("ncqq_limit_invalid") from exc
        containers = await self._containers()
        if status:
            containers = [item for item in containers if str(item.get("status") or "").lower() == status]
        if keyword:
            containers = [item for item in containers if keyword in str(item.get("name") or "").casefold()]
        total = len(containers)
        visible = [_project_instance(item) for item in containers[:limit]]
        offline = sum(not bool(item.get("bot_online")) for item in visible)
        return {
            "ok": True,
            "capability": self.list_capability,
            "read_only": True,
            "instances": visible,
            "count": total,
            "returned_count": len(visible),
            "result_summary": f"NCQQ instances: {total}; offline in result: {offline}",
        }

    async def get_login_status(self, arguments: dict[str, Any], credential_ref: str) -> dict[str, Any]:
        if credential_ref or set(arguments) - {"name"}:
            raise CapabilityError("ncqq_arguments_not_allowed")
        name = str(arguments.get("name") or "").strip()
        if not name or len(name) > 64:
            raise CapabilityError("ncqq_name_required")
        target = next((item for item in await self._containers() if str(item.get("name") or "") == name), None)
        if target is None:
            raise CapabilityError("ncqq_instance_not_found")
        projected = _project_instance(target)
        state = "online" if projected["bot_online"] else str(projected.get("status") or "offline")
        return {
            "ok": True,
            "capability": self.status_capability,
            "read_only": True,
            "instance": projected,
            "result_summary": f"NCQQ {name}: {state}",
        }

    async def _containers(self) -> list[dict[str, Any]]:
        if not _is_private_url(self.base_url):
            raise CapabilityError("ncqq_url_not_private")
        session = self.session_getter()
        if session is None:
            raise CapabilityError("http_session_unavailable")
        try:
            async with session.get(
                f"{self.base_url}/api/public/containers",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise CapabilityError(f"ncqq_http_{response.status}")
        except aiohttp.ClientError as exc:
            raise CapabilityError("ncqq_request_failed") from exc
        items = data.get("containers") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise CapabilityError("ncqq_response_invalid")
        return [item for item in items if isinstance(item, dict)]


def _project_instance(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or "")[:64],
        "status": str(item.get("status") or "")[:32],
        "node_id": str(item.get("node_id") or "local")[:64],
        "uin": str(item.get("uin") or "")[:32],
        "bot_online": bool(item.get("bot_online")),
        "heartbeat_ts": int(item.get("bot_heartbeat_ts") or 0),
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
