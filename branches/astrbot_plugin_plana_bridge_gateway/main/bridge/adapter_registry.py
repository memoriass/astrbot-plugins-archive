from __future__ import annotations

from typing import Any

from .adapters import AniRssReadOnlyAdapter, KomgaReadOnlyAdapter, NcqqReadOnlyAdapter, QBittorrentReadOnlyAdapter
from .capability import CapabilityRegistry
from ..plugin.config import safe_int


def build_capability_registry(
    *, config: dict[str, Any], credential_provider: Any, session_getter: Any
) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    if bool(config.get("enable_ani_rss_adapter", False)):
        adapter = AniRssReadOnlyAdapter(
            base_url=str(config.get("ani_rss_base_url", "") or ""),
            api_prefix=str(config.get("ani_rss_api_prefix", "/api") or "/api"),
            credential_provider=credential_provider,
            session_getter=session_getter,
            timeout_seconds=safe_int(config.get("ani_rss_timeout_seconds", 10), 10, 1, 60),
            allow_private_network_only=True,
        )
        registry.register(adapter.service_ref, adapter.capability_name, adapter.list_subscriptions)
    if bool(config.get("enable_ncqq_adapter", False)):
        adapter = NcqqReadOnlyAdapter(
            base_url=str(config.get("ncqq_base_url", "") or ""),
            session_getter=session_getter,
            timeout_seconds=safe_int(config.get("ncqq_timeout_seconds", 10), 10, 1, 60),
        )
        registry.register(adapter.service_ref, adapter.list_capability, adapter.list_instances)
        registry.register(adapter.service_ref, adapter.status_capability, adapter.get_login_status)
    if bool(config.get("enable_qbittorrent_adapter", False)):
        adapter = QBittorrentReadOnlyAdapter(
            base_url=str(config.get("qbittorrent_base_url", "") or ""),
            session_getter=session_getter,
            timeout_seconds=safe_int(config.get("qbittorrent_timeout_seconds", 10), 10, 1, 60),
        )
        registry.register(adapter.service_ref, adapter.list_capability, adapter.list_torrents)
        registry.register(adapter.service_ref, adapter.transfer_capability, adapter.transfer_status)
    if bool(config.get("enable_komga_adapter", False)):
        adapter = KomgaReadOnlyAdapter(
            base_url=str(config.get("komga_base_url", "") or ""),
            credential_provider=credential_provider,
            session_getter=session_getter,
            timeout_seconds=safe_int(config.get("komga_timeout_seconds", 10), 10, 1, 60),
        )
        handlers = {
            "komga.list_libraries": adapter.list_libraries,
            "komga.search_series": adapter.search_series,
            "komga.list_recent": adapter.list_recent,
        }
        for capability in adapter.capabilities:
            registry.register(adapter.service_ref, capability, handlers[capability])
    return registry
