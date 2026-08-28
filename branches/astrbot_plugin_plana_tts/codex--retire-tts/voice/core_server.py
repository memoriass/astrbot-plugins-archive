from __future__ import annotations

import secrets
from typing import Any

from aiohttp import web


class PlanaTTSLoopbackServer:
    """Token-protected loopback fallback for split-process Core deployments."""

    def __init__(self, service: Any, *, enabled: bool, port: int, core_service_key: str) -> None:
        self.service = service
        self.enabled = enabled
        self.port = max(1024, min(int(port or 6191), 65535))
        self.core_service_key = str(core_service_key or "").strip()
        self._runner: web.AppRunner | None = None

    async def start(self) -> bool:
        if not self.enabled or not self.core_service_key or self._runner is not None:
            return False
        app = web.Application(client_max_size=64 * 1024)
        app.router.add_get("/health", self._health)
        app.router.add_get("/plana_tts/state", self._state)
        app.router.add_post("/plana_tts/synthesize", self._synthesize)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        try:
            await web.TCPSite(self._runner, "127.0.0.1", self.port).start()
        except Exception:
            await self.stop()
            raise
        return True

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, request: web.Request) -> web.Response:
        return self._response(request, self.service.status())

    async def _state(self, request: web.Request) -> web.Response:
        return self._response(request, self.service.status())

    async def _synthesize(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        result = await self.service.synthesize(payload if isinstance(payload, dict) else {})
        return web.json_response(result, status=200 if result.get("ok", False) else 400)

    def _response(self, request: web.Request, result: dict[str, Any]) -> web.Response:
        if not self._authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return web.json_response(result, status=200 if result.get("ok", False) else 400)

    def _authorized(self, request: web.Request) -> bool:
        supplied = str(request.headers.get("X-Plana-Core-Key") or "").strip()
        return (
            request.remote in {"127.0.0.1", "::1"}
            and bool(supplied)
            and secrets.compare_digest(supplied, self.core_service_key)
        )
