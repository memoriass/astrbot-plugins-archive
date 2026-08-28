from __future__ import annotations

from ..assets.semantic import semantic_candidate as _semantic_candidate
from ..assets.semantic import tag_candidate as _tag_candidate

from quart import jsonify, request

from ..assets import REVIEW_TAG


class TaggingApiMixin:
    async def _api_asset_candidate_feedback(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        result = self.store.candidate_feedback(
            request_id=str(payload.get("request_id") or ""),
            asset_ref=str(payload.get("asset_ref") or ""),
            action=str(payload.get("action") or ""),
            query=str(payload.get("query") or ""),
            reason=str(payload.get("reason") or ""),
        )
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_asset_semantic_candidates(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        query = str(request.args.get("q", "") or "")
        tag = str(request.args.get("tag", "") or "").strip().lower()
        limit = _safe_int(request.args.get("limit"), 20, 1, 100)
        known_tags = set(self.store.status().get("tag_list", []))
        assets = self.store.list_assets(query=query, tag=tag, limit=200)
        candidates = []
        for asset in assets:
            candidate = _tag_candidate(asset, known_tags)
            candidates.append(_semantic_candidate(candidate))
            if len(candidates) >= limit:
                break
        return jsonify(
            {
                "ok": True,
                "candidate_only": True,
                "semantic_candidate_policy": {
                    "candidate_only": True,
                    "production_still_uses_controlled_tags": True,
                    "needs_review_is_not_production_eligible": True,
                },
                "assets": candidates,
            }
        )

    async def _api_tagging_candidates(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        mode = str(request.args.get("mode", "all") or "all")
        query = str(request.args.get("q", "") or "")
        include_tag = str(request.args.get("include_tag", "") or "").strip().lower()
        exclude_tag = str(request.args.get("exclude_tag", "") or "").strip().lower()
        min_confidence = _safe_int(request.args.get("min_confidence"), 0, 0, 100)
        limit = _safe_int(request.args.get("limit"), 80, 1, 200)
        assets = self.store.list_assets(query=query, tag=include_tag, limit=200)
        known_tags = set(self.store.status().get("tag_list", []))
        candidates = []
        for asset in assets:
            tags = set(asset.get("tags", []))
            if exclude_tag and exclude_tag in tags:
                continue
            candidate = _tag_candidate(asset, known_tags)
            confidence = int(candidate["confidence"])
            pending = not tags or tags == {REVIEW_TAG}
            if mode == "untagged" and not pending:
                continue
            if mode == "tagged" and pending:
                continue
            if mode == "needs_review" and not pending and confidence >= 70:
                continue
            if min_confidence and confidence < min_confidence:
                continue
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return jsonify({"ok": True, "assets": candidates, "mode": mode})

    async def _api_tagging_batch(self):
        if not self._authorized(readonly=False):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        raw_ids = payload.get("ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({"ok": False, "error": "missing_ids"}), 400
        add_tags = _tags(payload.get("add_tags", []))
        remove_tags = set(_tags(payload.get("remove_tags", [])))
        set_tags = payload.get("set_tags")
        approve = bool(payload.get("approve", False))
        updated = []
        failed = []
        for raw_id in raw_ids:
            asset_id = _safe_int(raw_id, 0, 1, 2_147_483_647)
            asset = self.store.get_asset(asset_id)
            if not asset:
                failed.append({"id": raw_id, "error": "not_found"})
                continue
            tags = _tags(set_tags) if set_tags is not None else list(asset["tags"])
            tags = [tag for tag in tags if tag not in remove_tags]
            for tag in add_tags:
                if tag not in tags:
                    tags.append(tag)
            result = self.store.update_asset(asset_id, tags=tags, approve=approve)
            if result.get("ok"):
                asset = result["asset"]
                updated.append(asset)
            else:
                failed.append({"id": asset_id, "error": result.get("error")})
        return jsonify(
            {"ok": not failed, "updated": updated, "failed": failed, "count": len(updated)}
        )

    async def _api_tagging_analyze(self):
        if not self._authorized(readonly=True):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        ids = payload.get("ids", []) if isinstance(payload, dict) else []
        known_tags = set(self.store.status().get("tag_list", []))
        assets = []
        iterable = ids[:100] if isinstance(ids, list) else []
        for raw_id in iterable:
            asset = self.store.get_asset(_safe_int(raw_id, 0, 1, 2_147_483_647))
            if asset:
                assets.append(_tag_candidate(asset, known_tags))
        return jsonify(
            {
                "ok": True,
                "engine": "local_rules",
                "semantic_candidate_policy": {
                    "candidate_only": True,
                    "production_still_uses_controlled_tags": True,
                    "needs_review_is_not_production_eligible": True,
                },
                "ai_enabled": bool(self.config.get("tagging_ai_enabled", False)),
                "provider": str(self.config.get("tagging_ai_provider", "local") or "local"),
                "assets": assets,
            }
        )


def _safe_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _tags(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace("\n", ",").replace("，", ",").replace("、", ",").split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result = []
    for item in raw:
        text = str(item).strip().lower()
        if text and text not in result:
            result.append(text)
    return result
