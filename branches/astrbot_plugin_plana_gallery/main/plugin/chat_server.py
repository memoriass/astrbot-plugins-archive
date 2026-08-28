from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web


class GalleryLoopbackServer:
    """Optional token-protected HTTP fallback bound only to loopback."""

    def __init__(
        self,
        service: Any,
        *,
        enabled: bool,
        port: int,
        core_service_key: str,
    ) -> None:
        self.service = service
        self.enabled = enabled
        self.port = max(1024, min(int(port or 6193), 65535))
        self.core_service_key = str(core_service_key or "").strip()
        self._runner: web.AppRunner | None = None

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.core_service_key)

    async def start(self) -> bool:
        if not self.configured or self._runner is not None:
            return False
        app = web.Application(client_max_size=64 * 1024)
        app.router.add_get("/health", self._health)
        app.router.add_post(
            "/plana_gallery/api/chat/candidates",
            self._candidates,
        )
        app.router.add_post(
            "/plana_gallery/api/chat/feedback",
            self._feedback,
        )
        app.router.add_get(
            "/plana_gallery/api/chat/resolve",
            self._resolve,
        )
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        try:
            await site.start()
        except Exception:
            await self.stop()
            raise
        return True

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return web.json_response(self.service.status())

    async def _candidates(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        payload = await self._payload(request)
        result = self.service.candidates(payload)
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _feedback(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        payload = await self._payload(request)
        result = self.service.feedback(payload)
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def _resolve(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        result = self.service.resolve(str(request.query.get("asset_ref") or ""))
        return web.json_response(result, status=200 if result.get("ok") else 404)

    def _authorized(self, request: web.Request) -> bool:
        if request.remote not in {"127.0.0.1", "::1"}:
            return False
        supplied = str(request.headers.get("X-Plana-Core-Key") or "").strip()
        return bool(supplied) and secrets.compare_digest(supplied, self.core_service_key)

    @staticmethod
    async def _payload(request: web.Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}
