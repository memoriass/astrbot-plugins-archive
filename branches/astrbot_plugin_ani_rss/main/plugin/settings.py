from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..integrations.ani_rss import AniRssClient, AniRssError
from ..routing.commands import (
    format_command,
    normalize_wake_prefixes,
)


class PluginSettingsMixin:
    def _cfg(self, key: str, default: Any) -> Any:
        value = self.config.get(key, default)
        return default if value is None else value

    def client(self, *, require_api_key: bool = False) -> AniRssClient:
        api_key = str(self._cfg("api_key", "") or "").strip()
        if require_api_key and not api_key:
            raise AniRssError("ANI-RSS api_key is not configured.")
        return AniRssClient(
            base_url=str(self._cfg("base_url", "http://127.0.0.1:7789")),
            api_prefix=str(self._cfg("api_prefix", "/api")),
            api_key=api_key,
            timeout_seconds=int(self._cfg("timeout_seconds", 30)),
        )

    def workflow_timeout_seconds(self) -> int:
        try:
            value = self._cfg(
                "interaction_timeout_seconds",
                self._cfg("workflow_confirm_timeout_seconds", 120),
            )
            return max(int(value), 10)
        except (TypeError, ValueError):
            return 120

    def pending_task_ttl_seconds(self) -> int:
        try:
            return max(int(self._cfg("pending_task_ttl_seconds", 86400)), 60)
        except (TypeError, ValueError):
            return 86400

    def subscription_cache_ttl_seconds(self) -> int:
        try:
            return max(int(self._cfg("subscription_cache_ttl_seconds", 300)), 0)
        except (TypeError, ValueError):
            return 300

    def mikan_search_cache_ttl_seconds(self) -> int:
        try:
            return max(int(self._cfg("mikan_search_cache_ttl_seconds", 3600)), 0)
        except (TypeError, ValueError):
            return 3600

    def storage_cleanup_interval_seconds(self) -> int:
        try:
            return max(int(self._cfg("storage_cleanup_interval_seconds", 600)), 60)
        except (TypeError, ValueError):
            return 600

    def command_prefixes(self, event: Any | None = None) -> list[str]:
        umo = str(getattr(event, "unified_msg_origin", "") or "") if event else ""
        config: Any = None
        get_config = getattr(self.context, "get_config", None)
        if callable(get_config):
            with suppress(Exception):
                config = get_config(umo or None)
        if config is not None and hasattr(config, "get"):
            with suppress(Exception):
                return normalize_wake_prefixes(config.get("wake_prefix", ["/"]))
        with suppress(Exception):
            from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH

            path = Path(ASTRBOT_CONFIG_PATH)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return normalize_wake_prefixes(data.get("wake_prefix", ["/"]))
        return ["/"]

    def command_example(self, command: str, event: Any | None = None) -> str:
        prefix = self.command_prefixes(event)[0]
        return format_command(prefix, command)

    def render_mode(self) -> str:
        mode = str(self._cfg("render_mode", "image") or "image").strip().lower()
        if mode not in {"text", "image", "both"}:
            return "image"
        return mode

    def render_width(self) -> int:
        return 860

    def render_scale(self) -> int:
        return 2

    def render_output_dir(self) -> str:
        return ""

    def cover_proxy_config(self) -> dict[str, Any]:
        api_prefix = str(self._cfg("api_prefix", "/api") or "/api")
        if api_prefix and not api_prefix.startswith("/"):
            api_prefix = f"/{api_prefix}"
        try:
            timeout_seconds = int(self._cfg("timeout_seconds", 30))
        except (TypeError, ValueError):
            timeout_seconds = 30
        return {
            "base_url": str(self._cfg("base_url", "http://127.0.0.1:7789") or "").rstrip("/"),
            "api_prefix": api_prefix.rstrip("/"),
            "api_key": str(self._cfg("api_key", "") or "").strip(),
            "timeout_seconds": timeout_seconds,
        }
