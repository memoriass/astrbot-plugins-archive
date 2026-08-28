from __future__ import annotations

from astrbot.api.star import register

from .plugin.runtime import PlanaGalleryPlugin as _PlanaGalleryPlugin


@register(
    "astrbot_plugin_plana_gallery",
    "soulter",
    "Plana local context gallery, review, tagging, and chat image retrieval.",
    "0.3.0",
    "https://github.com/memoriass/astrbot_plugin_plana_gallery",
)
class PlanaGalleryPlugin(_PlanaGalleryPlugin):
    pass

__all__ = ["PlanaGalleryPlugin"]
