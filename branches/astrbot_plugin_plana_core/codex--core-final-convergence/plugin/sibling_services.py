from __future__ import annotations

from typing import Any


def find_sibling_service(
    runtime: Any,
    *,
    plugin_name: str,
    service_attr: str,
    required_methods: tuple[str, ...],
) -> Any | None:
    """Find a controlled service object exported by a loaded sibling plugin."""

    registry = getattr(runtime, "sibling_services", None)
    if isinstance(registry, dict):
        service = registry.get(plugin_name)
        if _valid_service(service, required_methods):
            return service

    context = getattr(runtime, "astr_context", None)
    get_all = getattr(context, "get_all_stars", None)
    stars: list[Any] = []
    if callable(get_all):
        try:
            stars = list(get_all() or [])
        except Exception:  # noqa: BLE001
            stars = []
    try:
        from astrbot.core.star.star import star_map

        stars.extend(star_map.values())
    except (ImportError, AttributeError):
        pass

    seen: set[int] = set()
    for metadata in stars:
        identity = id(metadata)
        if identity in seen:
            continue
        seen.add(identity)
        if not _matches(metadata, plugin_name):
            continue
        plugin = getattr(metadata, "star_cls", None)
        if plugin is None or not bool(getattr(plugin, "enabled", True)):
            continue
        service = getattr(plugin, service_attr, None)
        if _valid_service(service, required_methods):
            return service
    return None


def _matches(metadata: Any, plugin_name: str) -> bool:
    root_name = str(getattr(metadata, "root_dir_name", "") or "")
    module_path = str(getattr(metadata, "module_path", "") or "")
    name = str(getattr(metadata, "name", "") or "")
    return root_name == plugin_name or plugin_name in module_path or name == plugin_name


def _valid_service(service: Any, required_methods: tuple[str, ...]) -> bool:
    return service is not None and all(
        callable(getattr(service, method, None)) for method in required_methods
    )
