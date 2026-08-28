from __future__ import annotations

from typing import Any


def _argument(
    name: str,
    value_type: str,
    *,
    required: bool = False,
    default: Any = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    result = {"name": name, "type": value_type, "required": required}
    if default is not None:
        result["default"] = default
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    return result


ADAPTER_CATALOG: dict[str, dict[str, Any]] = {
    "ani_rss.production": {
        "name": "ANI-RSS",
        "copy_key": "gateway.adapter.ani_rss",
        "target": "200 · ANI-RSS",
        "deployment": "192.168.1.200",
        "protocol": "HTTP/JSON · private LAN",
        "authentication": "Gateway managed API key",
        "authentication_key": "gateway.auth.managed_api_key",
        "trust_boundary": "NAS media services",
        "trust_boundary_key": "gateway.trust.nas_media",
        "credential_ref": "ani_rss.production.api_key",
        "health_capability": "ani_rss.get_status",
    },
    "ncqq.production": {
        "name": "NCQQ",
        "copy_key": "gateway.adapter.ncqq",
        "target": "201 · NCQQ Manager",
        "deployment": "192.168.1.201",
        "protocol": "HTTP/JSON · private LAN",
        "authentication": "Internal service authentication",
        "authentication_key": "gateway.auth.internal_service",
        "trust_boundary": "Messaging platform services",
        "trust_boundary_key": "gateway.trust.messaging",
        "credential_ref": "ncqq.production.api_key",
        "health_capability": "ncqq.get_manager_health",
    },
    "qbittorrent.production": {
        "name": "qBittorrent",
        "copy_key": "gateway.adapter.qbittorrent",
        "target": "200 · qBittorrent",
        "deployment": "192.168.1.200",
        "protocol": "qBittorrent Web API · private LAN",
        "authentication": "Gateway managed connection",
        "authentication_key": "gateway.auth.managed_connection",
        "trust_boundary": "NAS download services",
        "trust_boundary_key": "gateway.trust.nas_download",
        "credential_ref": "",
        "health_capability": "qbittorrent.transfer_status",
        "owner": "core",
        "management": "controlled",
    },
    "qbittorrent.tianxue": {
        "name": "qBittorrent · Tianxue",
        "copy_key": "gateway.adapter.qbittorrent_tianxue",
        "target": "200 · tianxue_qbittorrent :11080",
        "deployment": "192.168.1.200:11080",
        "protocol": "qBittorrent Web API · read-only",
        "authentication": "Owned by Tianxue seeding",
        "authentication_key": "gateway.auth.external_owner",
        "trust_boundary": "Dedicated seeding service",
        "trust_boundary_key": "gateway.trust.tianxue_owned",
        "credential_ref": "",
        "health_capability": "tianxue_qb.transfer_status",
        "owner": "tianxue",
        "management": "read_only_external",
    },
    "komga.production": {
        "name": "Komga",
        "copy_key": "gateway.adapter.komga",
        "target": "200 · Komga",
        "deployment": "192.168.1.200",
        "protocol": "Komga REST API · private LAN",
        "authentication": "X-API-Key",
        "authentication_key": "gateway.auth.x_api_key",
        "trust_boundary": "NAS media services",
        "trust_boundary_key": "gateway.trust.nas_media",
        "credential_ref": "komga.production.readonly",
        "health_capability": "komga.list_libraries",
    },
}


EXTRA_CAPABILITY_CATALOG = {
    "ncqq.get_manager_health": {"copy_key": "gateway.capability.ncqq_health", "category": "status", "result_type": "health_status", "arguments": ()},
    "ncqq.list_bots": {"copy_key": "gateway.capability.ncqq_bots", "category": "catalog", "result_type": "bot_list", "arguments": (_argument("connected", "boolean"), _argument("keyword", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ncqq.list_bot_heartbeats": {"copy_key": "gateway.capability.ncqq_heartbeats", "category": "status", "result_type": "heartbeat_list", "arguments": (_argument("online", "boolean"), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ncqq.get_stats": {"copy_key": "gateway.capability.ncqq_stats", "category": "status", "result_type": "runtime_stats", "arguments": (_argument("name", "string", required=True),)},
    "ncqq.get_recent_logs": {"copy_key": "gateway.capability.ncqq_logs", "category": "activity", "result_type": "redacted_logs", "arguments": (_argument("name", "string", required=True), _argument("lines", "integer", default=30, minimum=1, maximum=100))},
    "ncqq.list_backend_endpoints": {"copy_key": "gateway.capability.ncqq_backends", "category": "catalog", "result_type": "backend_endpoint_list", "arguments": (_argument("keyword", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ncqq.list_assets": {"copy_key": "gateway.capability.ncqq_assets", "category": "catalog", "result_type": "asset_list", "arguments": (_argument("limit", "integer", default=100, minimum=1, maximum=100),)},
    "ncqq.list_instance_files": {"copy_key": "gateway.capability.ncqq_files", "category": "detail", "result_type": "file_list", "arguments": (_argument("name", "string", required=True), _argument("path", "string"), _argument("limit", "integer", default=100, minimum=1, maximum=100))},
    "ncqq.read_instance_config": {"copy_key": "gateway.capability.ncqq_config", "category": "detail", "result_type": "redacted_config", "arguments": (_argument("name", "string", required=True), _argument("file_name", "string", required=True), _argument("lines", "integer", default=20, minimum=1, maximum=50))},
    "ncqq.get_botshepherd_status": {"copy_key": "gateway.capability.ncqq_botshepherd", "category": "status", "result_type": "service_status", "arguments": ()},
    "ncqq.get_activation_status": {"copy_key": "gateway.capability.ncqq_activation", "category": "status", "result_type": "activation_status", "arguments": ()},
    "ncqq.control_instance": {"copy_key": "gateway.capability.ncqq_control", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("name", "string", required=True), _argument("action", "string", required=True))},
    "ncqq.create_instance": {"copy_key": "gateway.capability.ncqq_create", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("name", "string", required=True),)},
    "ncqq.refresh_login": {"copy_key": "gateway.capability.ncqq_refresh_login", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("name", "string", required=True),)},
    "ncqq.inject_backend": {"copy_key": "gateway.capability.ncqq_inject_backend", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("name", "string", required=True), _argument("alias", "string", required=True))},
    "ncqq.delete_instance_keep_data": {"copy_key": "gateway.capability.ncqq_delete_keep", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("name", "string", required=True),)},
    "ani_rss.get_status": {"copy_key": "gateway.capability.ani_status", "category": "status", "result_type": "service_status", "arguments": ()},
    "ani_rss.get_about": {"copy_key": "gateway.capability.ani_about", "category": "detail", "result_type": "service_about", "arguments": ()},
    "ani_rss.preview_subscription": {"copy_key": "gateway.capability.ani_preview", "category": "detail", "result_type": "preview_items", "arguments": (_argument("id", "string", required=True), _argument("limit", "integer", default=20, minimum=1, maximum=100))},
    "ani_rss.build_subscription_from_rss": {"copy_key": "gateway.capability.ani_build", "category": "detail", "result_type": "subscription_candidate", "arguments": (_argument("rss_url", "string", required=True), _argument("rss_type", "string", default="mikan"), _argument("bgm_url", "string"), _argument("subgroup", "string"), _argument("enable", "boolean", default=True))},
    "ani_rss.search_mikan": {"copy_key": "gateway.capability.ani_mikan_search", "category": "search", "result_type": "catalog_matches", "arguments": (_argument("query", "string", required=True), _argument("year", "integer"), _argument("season", "string"), _argument("limit", "integer", default=20, minimum=1, maximum=100))},
    "ani_rss.list_mikan_groups": {"copy_key": "gateway.capability.ani_mikan_groups", "category": "catalog", "result_type": "subtitle_group_list", "arguments": (_argument("url", "string", required=True), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ani_rss.list_anibt_season": {"copy_key": "gateway.capability.ani_anibt_season", "category": "catalog", "result_type": "catalog_list", "arguments": (_argument("season", "string"), _argument("bgm_url", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ani_rss.list_anibt_groups": {"copy_key": "gateway.capability.ani_anibt_groups", "category": "catalog", "result_type": "subtitle_group_list", "arguments": (_argument("bgm_id", "string", required=True), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ani_rss.list_anime_garden": {"copy_key": "gateway.capability.ani_garden_list", "category": "catalog", "result_type": "catalog_list", "arguments": (_argument("bgm_url", "string"), _argument("query", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ani_rss.list_anime_garden_groups": {"copy_key": "gateway.capability.ani_garden_groups", "category": "catalog", "result_type": "subtitle_group_list", "arguments": (_argument("bgm_id", "string", required=True), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "ani_rss.list_download_tasks": {"copy_key": "gateway.capability.ani_qb_list", "category": "catalog", "result_type": "torrent_list", "arguments": (_argument("filter", "string"), _argument("category", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=200))},
    "ani_rss.download_transfer_status": {"copy_key": "gateway.capability.ani_qb_transfer", "category": "status", "result_type": "transfer_status", "arguments": ()},
    "ani_rss.get_download_task": {"copy_key": "gateway.capability.ani_qb_get", "category": "detail", "result_type": "torrent_detail", "arguments": (_argument("hash", "string"), _argument("name", "string")), "require_one_of": ("hash", "name")},
    "ani_rss.list_download_files": {"copy_key": "gateway.capability.ani_qb_files", "category": "detail", "result_type": "file_list", "arguments": (_argument("hash", "string", required=True), _argument("limit", "integer", default=100, minimum=1, maximum=200))},
    "ani_rss.list_download_categories": {"copy_key": "gateway.capability.ani_qb_categories", "category": "catalog", "result_type": "category_list", "arguments": ()},
    "ani_rss.get_download_properties": {"copy_key": "gateway.capability.ani_qb_properties", "category": "detail", "result_type": "torrent_properties", "arguments": (_argument("hash", "string", required=True),)},
    "ani_rss.list_download_trackers": {"copy_key": "gateway.capability.ani_qb_trackers", "category": "detail", "result_type": "tracker_list", "arguments": (_argument("hash", "string", required=True),)},
    "ani_rss.add_subscription_from_rss": {"copy_key": "gateway.capability.ani_add", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("rss_url", "string", required=True), _argument("rss_type", "string", default="mikan"), _argument("bgm_url", "string"), _argument("subgroup", "string"), _argument("enable", "boolean", default=True))},
    "ani_rss.set_subscription_enabled": {"copy_key": "gateway.capability.ani_enable", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("id", "string", required=True), _argument("enabled", "boolean", required=True))},
    "ani_rss.refresh_subscription": {"copy_key": "gateway.capability.ani_refresh", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("id", "string", required=True),)},
    "ani_rss.refresh_all": {"copy_key": "gateway.capability.ani_refresh_all", "category": "control", "result_type": "operation_receipt", "arguments": ()},
    "ani_rss.delete_subscription": {"copy_key": "gateway.capability.ani_delete", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("id", "string", required=True),)},
    "qbittorrent.list_categories": {"copy_key": "gateway.capability.qb_categories", "category": "catalog", "result_type": "category_list", "arguments": ()},
    "qbittorrent.get_properties": {"copy_key": "gateway.capability.qb_properties", "category": "detail", "result_type": "torrent_properties", "arguments": (_argument("hash", "string", required=True),)},
    "qbittorrent.list_trackers": {"copy_key": "gateway.capability.qb_trackers", "category": "detail", "result_type": "tracker_list", "arguments": (_argument("hash", "string", required=True),)},
    "qbittorrent.add_torrent_url": {"copy_key": "gateway.capability.qb_add", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("url", "string", required=True), _argument("category", "string"), _argument("paused", "boolean", default=False))},
    "qbittorrent.control_torrent": {"copy_key": "gateway.capability.qb_control", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("hash", "string", required=True), _argument("action", "string", required=True))},
    "qbittorrent.set_category": {"copy_key": "gateway.capability.qb_set_category", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("hash", "string", required=True), _argument("category", "string"))},
    "qbittorrent.delete_torrent_keep_files": {"copy_key": "gateway.capability.qb_delete_keep", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("hash", "string", required=True),)},
    "tianxue_qb.list_torrents": {"copy_key": "gateway.capability.tianxue_qb_list", "category": "catalog", "result_type": "torrent_list", "arguments": (_argument("filter", "string"), _argument("category", "string"), _argument("limit", "integer", default=50, minimum=1, maximum=200))},
    "tianxue_qb.transfer_status": {"copy_key": "gateway.capability.tianxue_qb_transfer", "category": "status", "result_type": "transfer_status", "arguments": ()},
    "tianxue_qb.get_torrent": {"copy_key": "gateway.capability.tianxue_qb_get", "category": "detail", "result_type": "torrent_detail", "arguments": (_argument("hash", "string"), _argument("name", "string")), "require_one_of": ("hash", "name")},
    "tianxue_qb.list_files": {"copy_key": "gateway.capability.tianxue_qb_files", "category": "detail", "result_type": "file_list", "arguments": (_argument("hash", "string", required=True), _argument("limit", "integer", default=100, minimum=1, maximum=200))},
    "tianxue_qb.list_categories": {"copy_key": "gateway.capability.tianxue_qb_categories", "category": "catalog", "result_type": "category_list", "arguments": ()},
    "tianxue_qb.get_properties": {"copy_key": "gateway.capability.tianxue_qb_properties", "category": "detail", "result_type": "torrent_properties", "arguments": (_argument("hash", "string", required=True),)},
    "tianxue_qb.list_trackers": {"copy_key": "gateway.capability.tianxue_qb_trackers", "category": "detail", "result_type": "tracker_list", "arguments": (_argument("hash", "string", required=True),)},
    "komga.get_library": {"copy_key": "gateway.capability.komga_library", "category": "detail", "result_type": "library_detail", "arguments": (_argument("library_id", "string", required=True),)},
    "komga.list_series_latest": {"copy_key": "gateway.capability.komga_latest", "category": "activity", "result_type": "series_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.list_series_new": {"copy_key": "gateway.capability.komga_new", "category": "activity", "result_type": "series_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.list_series_updated": {"copy_key": "gateway.capability.komga_updated", "category": "activity", "result_type": "series_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.get_series": {"copy_key": "gateway.capability.komga_series", "category": "detail", "result_type": "series_detail", "arguments": (_argument("series_id", "string", required=True),)},
    "komga.list_series_books": {"copy_key": "gateway.capability.komga_series_books", "category": "catalog", "result_type": "book_list", "arguments": (_argument("series_id", "string", required=True), _argument("limit", "integer", default=50, minimum=1, maximum=100))},
    "komga.get_book": {"copy_key": "gateway.capability.komga_book", "category": "detail", "result_type": "book_detail", "arguments": (_argument("book_id", "string", required=True),)},
    "komga.list_on_deck": {"copy_key": "gateway.capability.komga_on_deck", "category": "activity", "result_type": "book_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.list_collections": {"copy_key": "gateway.capability.komga_collections", "category": "catalog", "result_type": "collection_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.list_readlists": {"copy_key": "gateway.capability.komga_readlists", "category": "catalog", "result_type": "readlist_list", "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),)},
    "komga.scan_library": {"copy_key": "gateway.capability.komga_scan", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("library_id", "string", required=True),)},
    "komga.analyze_library": {"copy_key": "gateway.capability.komga_analyze", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("library_id", "string", required=True),)},
    "komga.refresh_library_metadata": {"copy_key": "gateway.capability.komga_refresh_library", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("library_id", "string", required=True),)},
    "komga.refresh_series_metadata": {"copy_key": "gateway.capability.komga_refresh_series", "category": "control", "result_type": "operation_receipt", "arguments": (_argument("series_id", "string", required=True),)},
}


CAPABILITY_CATALOG: dict[str, dict[str, Any]] = {
    "ani_rss.list_subscriptions": {
        "copy_key": "gateway.capability.ani_list",
        "category": "catalog",
        "result_type": "subscription_list",
        "arguments": (
            _argument("enabled", "boolean", default=True),
            _argument("limit", "integer", default=50, minimum=1, maximum=200),
        ),
    },
    "ani_rss.list_recent_updates": {
        "copy_key": "gateway.capability.ani_recent",
        "category": "activity",
        "result_type": "update_list",
        "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=200),),
    },
    "ani_rss.get_subscription": {
        "copy_key": "gateway.capability.ani_get",
        "category": "detail",
        "result_type": "subscription_detail",
        "arguments": (_argument("id", "string"), _argument("title", "string")),
        "require_one_of": ("id", "title"),
    },
    "ani_rss.search_title": {
        "copy_key": "gateway.capability.ani_search",
        "category": "search",
        "result_type": "title_matches",
        "arguments": (
            _argument("query", "string", required=True),
            _argument("limit", "integer", default=20, minimum=1, maximum=200),
        ),
    },
    "ncqq.list_instances": {
        "copy_key": "gateway.capability.ncqq_list",
        "category": "catalog",
        "result_type": "instance_list",
        "arguments": (
            _argument("status", "string"),
            _argument("keyword", "string"),
            _argument("limit", "integer", default=50, minimum=1, maximum=100),
        ),
    },
    "ncqq.get_login_status": {
        "copy_key": "gateway.capability.ncqq_status",
        "category": "status",
        "result_type": "login_status",
        "arguments": (_argument("name", "string", required=True),),
    },
    "ncqq.fetch_qrcode": {
        "copy_key": "gateway.capability.ncqq_qrcode",
        "category": "artifact",
        "result_type": "png_artifact",
        "artifact": True,
        "arguments": (_argument("name", "string", required=True),),
    },
    "qbittorrent.list_torrents": {
        "copy_key": "gateway.capability.qb_list",
        "category": "catalog",
        "result_type": "torrent_list",
        "arguments": (
            _argument("filter", "string"),
            _argument("category", "string"),
            _argument("limit", "integer", default=50, minimum=1, maximum=100),
        ),
    },
    "qbittorrent.transfer_status": {
        "copy_key": "gateway.capability.qb_transfer",
        "category": "status",
        "result_type": "transfer_status",
        "arguments": (),
    },
    "qbittorrent.get_torrent": {
        "copy_key": "gateway.capability.qb_get",
        "category": "detail",
        "result_type": "torrent_detail",
        "arguments": (_argument("hash", "string"), _argument("name", "string")),
        "require_one_of": ("hash", "name"),
    },
    "qbittorrent.list_files": {
        "copy_key": "gateway.capability.qb_files",
        "category": "detail",
        "result_type": "file_list",
        "arguments": (
            _argument("hash", "string", required=True),
            _argument("limit", "integer", default=100, minimum=1, maximum=200),
        ),
    },
    "komga.list_libraries": {
        "copy_key": "gateway.capability.komga_libraries",
        "category": "catalog",
        "result_type": "library_list",
        "arguments": (),
    },
    "komga.search_series": {
        "copy_key": "gateway.capability.komga_search",
        "category": "search",
        "result_type": "series_matches",
        "arguments": (
            _argument("query", "string", required=True),
            _argument("limit", "integer", default=20, minimum=1, maximum=100),
        ),
    },
    "komga.list_recent": {
        "copy_key": "gateway.capability.komga_recent",
        "category": "activity",
        "result_type": "book_list",
        "arguments": (_argument("limit", "integer", default=20, minimum=1, maximum=100),),
    },
}

CAPABILITY_CATALOG.update(EXTRA_CAPABILITY_CATALOG)


def adapter_metadata(service_ref: str) -> dict[str, Any]:
    return dict(ADAPTER_CATALOG.get(service_ref, {}))


def capability_metadata(capability: str) -> dict[str, Any]:
    item = dict(CAPABILITY_CATALOG.get(capability, {}))
    item["arguments"] = [dict(argument) for argument in item.get("arguments") or ()]
    item["require_one_of"] = list(item.get("require_one_of") or ())
    return item
