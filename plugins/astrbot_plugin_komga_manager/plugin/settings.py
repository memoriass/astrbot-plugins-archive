from __future__ import annotations

from typing import Any

from ..integrations import KomgaClient


class PluginSettingsMixin:
    config: dict[str, Any]

    def client(self) -> KomgaClient:
        instance = getattr(self, "_komga_client", None)
        if instance is None:
            instance = KomgaClient(self.config)
            self._komga_client = instance
        return instance

    def default_limit(self) -> int:
        try:
            return max(1, min(int(self.config.get("default_limit") or 20), 100))
        except (TypeError, ValueError):
            return 20

    async def close_client(self) -> None:
        instance = getattr(self, "_komga_client", None)
        if instance is not None:
            await instance.close()
        self._komga_client = None

