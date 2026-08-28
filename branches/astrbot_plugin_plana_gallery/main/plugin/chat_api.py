from __future__ import annotations

from typing import Any

from quart import jsonify, request

class ChatAssetApiMixin:
    async def _api_chat_candidates(self):
        if not self._chat_authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.chat_service.candidates(payload)
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_chat_feedback(self):
        if not self._chat_authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.chat_service.feedback(payload)
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_chat_resolve(self):
        if not self._chat_authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        result = self.chat_service.resolve(str(request.args.get("asset_ref") or ""))
        return jsonify(result), 200 if result.get("ok") else 404

    async def _api_tag_taxonomy(self):
        if request.method == "GET":
            if not self._authorized(readonly=True):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            return jsonify({"ok": True, **self.store.tag_taxonomy()})
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.store.save_tag_definition(
            tag=str(payload.get("tag") or ""),
            label=str(payload.get("label") or ""),
            description=str(payload.get("description") or ""),
            aliases=_string_list(payload.get("aliases"), 50),
        )
        return jsonify(result), 200 if result.get("ok") else 400


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:160] for item in value[:limit] if str(item).strip()]
