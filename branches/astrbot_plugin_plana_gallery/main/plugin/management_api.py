from __future__ import annotations

import asyncio
from typing import Any

from quart import jsonify, make_response, request


class ManagementApiMixin:
    async def _api_asset_thumbnail(self, asset_id: str):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        result = self.store.thumbnail_status(
            int(asset_id), int(request.args.get("size", 320) or 320)
        )
        if result.get("ready"):
            data = await asyncio.to_thread(result["path"].read_bytes)
            response = await make_response(data)
            response.headers["Content-Type"] = str(result["mime_type"])
            response.headers["Cache-Control"] = "private, max-age=86400, immutable"
            response.headers["X-Plana-Thumbnail-Status"] = "ready"
            return response
        status = "invalid" if not result.get("ok") else "pending"
        response = await make_response(_thumbnail_placeholder(status))
        response.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Plana-Thumbnail-Status"] = status
        return response

    async def _api_asset_thumbnail_rebuild(self, asset_id: str):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        asset = self.store.get_asset(int(asset_id))
        if not asset:
            return jsonify({"ok": False, "error": "not_found"}), 404
        self.store.enqueue_thumbnail_job(
            int(asset["id"]), int(request.args.get("size", 320) or 320), str(asset["sha256"])
        )
        return jsonify({"ok": True, "status": "pending"}), 202

    async def _api_diagnostics_query(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.store.chat_diagnostics(
            request_id=str(payload.get("request_id") or "web-diagnostics"),
            query=str(payload.get("query") or ""),
            facets=_strings(payload.get("facets"), 12),
            emotions=_diagnostic_emotions(payload.get("emotions")),
            exclude_asset_refs=_strings(payload.get("exclude_asset_refs"), 100),
            limit=_integer(payload.get("limit"), 6, 1, 12),
            direct_score=float(payload.get("direct_score") or 50),
            direct_margin=float(payload.get("direct_margin") or 12),
        )
        return jsonify({"ok": True, **result})

    async def _api_diagnostics_feedback(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        action = str(payload.get("action") or "skipped").strip().lower()
        event = {"useful": "selected", "negative": "negative", "skipped": "skipped"}.get(
            action, action
        )
        result = self.store.record_chat_feedback(
            event_id=str(payload.get("event_id") or ""),
            request_id=str(payload.get("request_id") or ""),
            asset_ref=str(payload.get("asset_ref") or ""),
            event=event,
            query=str(payload.get("query") or ""),
            reason=f"diagnostics:{str(payload.get('reason') or action)[:450]}",
        )
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_tag_definition(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.store.save_tag_definition(
            tag=str(payload.get("tag") or ""),
            label=str(payload.get("label") or ""),
            description=str(payload.get("description") or ""),
            aliases=_strings(payload.get("aliases"), 50),
        )
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_review_commit(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.store.review_commit(
            payload["changes"],
            add_tags=_strings(payload.get("add_tags"), 100),
            remove_tags=_strings(payload.get("remove_tags"), 100),
            emotion_profiles=_emotion_profiles(payload.get("emotion_profiles")),
            approve=bool(payload.get("approve", False)),
        )
        status = 200 if result.get("ok") else (409 if result.get("error") == "version_conflict" else 400)
        return jsonify(result), status

    async def _api_jobs(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify(self.store.jobs_status(_integer(request.args.get("limit"), 50, 1, 200)))


def _strings(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:160] for item in value[:limit] if str(item).strip()]


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _emotion_profiles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("emotion_tag") or item.get("tag") or "").strip().lower()[:80]
        if tag.startswith("emotion:"):
            result.append(
                {
                    "emotion_tag": tag,
                    "intensity": _integer(item.get("intensity"), 2, 1, 3),
                    "prominence": "primary" if str(item.get("prominence")) == "primary" else "secondary",
                    "source": str(item.get("source") or "manual")[:32],
                    "suggestion_confidence": item.get("suggestion_confidence"),
                }
            )
    return result


def _diagnostic_emotions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("emotion_tag") or item.get("tag") or "").strip().lower()[:80]
        if not tag.startswith("emotion:"):
            continue
        try:
            weight = max(0.1, min(float(item.get("weight") or 1.0), 2.0))
        except (TypeError, ValueError):
            weight = 1.0
        result.append(
            {
                "emotion_tag": tag,
                "target_intensity": _integer(
                    item.get("target_intensity") or item.get("intensity"), 2, 1, 3
                ),
                "prominence": (
                    "primary" if str(item.get("prominence")) == "primary" else "secondary"
                ),
                "weight": weight,
            }
        )
    return result


def _thumbnail_placeholder(status: str) -> str:
    label = "Source unavailable" if status == "invalid" else "Generating thumbnail"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 240" role="img" aria-label="{label}">
<rect width="320" height="240" fill="#111827"/><path d="M96 164l42-44 30 30 24-25 32 39H96z" fill="#334155"/>
<circle cx="126" cy="91" r="16" fill="#475569"/><text x="160" y="205" text-anchor="middle" fill="#94a3b8" font-size="14">{label}</text></svg>"""
