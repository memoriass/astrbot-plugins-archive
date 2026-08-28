from __future__ import annotations

from quart import jsonify

from .diagnostics_payload import build_diagnostics_payload
from .resource_payload import build_resource_web_payload


class PlanaDiagnosticsAPIMixin:
    async def api_diagnostics(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        resources = await build_resource_web_payload(self.runtime, limit=100)
        return jsonify(
            {"ok": True, "data": build_diagnostics_payload(self.runtime, resources)}
        )
