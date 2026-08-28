from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import aiohttp

from ..capability import CapabilityError
from ..credential import CredentialError, CredentialProvider


class AniRssReadOnlyAdapter:
    service_ref = "ani_rss.production"
    capability_name = "ani_rss.list_subscriptions"

    def __init__(
        self,
        *,
        base_url: str,
        api_prefix: str,
        credential_provider: CredentialProvider,
        session_getter: Any,
        timeout_seconds: int,
        allow_private_network_only: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        prefix = api_prefix.strip().strip("/")
        self.api_prefix = f"/{prefix}" if prefix else ""
        self.credential_provider = credential_provider
        self.session_getter = session_getter
        self.timeout_seconds = max(1, min(int(timeout_seconds or 10), 60))
        self.allow_private_network_only = allow_private_network_only

    async def list_subscriptions(
        self,
        arguments: dict[str, Any],
        credential_ref: str,
    ) -> dict[str, Any]:
        if set(arguments) - {"enabled", "limit"}:
            raise CapabilityError("ani_rss_arguments_not_allowed")
        enabled = arguments.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise CapabilityError("ani_rss_enabled_invalid")
        try:
            limit = max(1, min(int(arguments.get("limit", 100) or 100), 200))
        except (TypeError, ValueError) as exc:
            raise CapabilityError("ani_rss_limit_invalid") from exc
        if self.allow_private_network_only and not _is_private_url(self.base_url):
            raise CapabilityError("ani_rss_url_not_private")
        session = self.session_getter()
        if session is None:
            raise CapabilityError("http_session_unavailable")
        headers = {"Accept": "application/json"}
        if credential_ref:
            try:
                credential = self.credential_provider.get(credential_ref)
            except CredentialError as exc:
                raise CapabilityError(str(exc)) from exc
            api_key = str(credential.get("api_key") or "")
            if not api_key:
                raise CapabilityError("ani_rss_api_key_missing")
            headers["api-key"] = api_key
        url = f"{self.base_url}{self.api_prefix}/listAni"
        try:
            async with session.post(
                url,
                json={},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    raise CapabilityError(f"ani_rss_http_{response.status}")
        except aiohttp.ClientError as exc:
            raise CapabilityError("ani_rss_request_failed") from exc
        subscriptions = _subscriptions(data)
        if enabled is not None:
            subscriptions = [item for item in subscriptions if bool(item.get("enable")) is enabled]
        total = len(subscriptions)
        visible = [_safe_projection(item) for item in subscriptions[:limit]]
        return {
            "ok": True,
            "capability": self.capability_name,
            "read_only": True,
            "subscriptions": visible,
            "count": total,
            "returned_count": len(visible),
            "result_summary": _result_summary(visible, total),
        }


def _subscriptions(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise CapabilityError("ani_rss_response_invalid")
    value = data.get("data", data)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("aniList", "list", "items", "subscriptions"):
            items = value.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        week_list = value.get("weekList")
        if isinstance(week_list, list):
            flattened: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for week in week_list:
                if not isinstance(week, dict) or not isinstance(week.get("items"), list):
                    continue
                for item in week["items"]:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id") or "").strip()
                    if item_id and item_id in seen_ids:
                        continue
                    if item_id:
                        seen_ids.add(item_id)
                    flattened.append(item)
            return flattened
    raise CapabilityError("ani_rss_response_invalid")


def _result_summary(subscriptions: list[dict[str, Any]], total: int) -> str:
    enabled_titles: list[str] = []
    for item in subscriptions:
        if not bool(item.get("enable")):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if title:
            enabled_titles.append(title)
        if len(enabled_titles) >= 10:
            break
    summary = f"ANI-RSS subscriptions: {total}"
    if len(subscriptions) != total:
        summary += f"; returned: {len(subscriptions)}"
    if enabled_titles:
        summary += "; enabled: " + ", ".join(enabled_titles)
    return summary


def _safe_projection(subscription: dict[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key in ("id", "title", "name", "enable", "season", "subgroup", "progress", "episode"):
        if key not in subscription:
            continue
        value = subscription.get(key)
        if isinstance(value, (bool, int, float)) or value is None:
            projected[key] = value
        elif isinstance(value, str):
            projected[key] = value[:300]
    return projected


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
