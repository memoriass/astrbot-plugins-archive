"""Compatibility wrapper for the moved ANI-RSS API client."""

from ..integrations.ani_rss import AniRssClient, AniRssError, flatten_ani_list

__all__ = ["AniRssClient", "AniRssError", "flatten_ani_list"]
