from __future__ import annotations

from quart import jsonify, request

from .domain_harness_payload import build_domain_harness_web_payload


def _safe_int(
    value: object,
    default: int,
    *,
    min_value: int = 1,
    max_value: int = 100,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


class PlanaWebAdminAPIMixin:
    async def api_domains(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify(
            {
                "ok": True,
                "data": {
                    "domain_harness": build_domain_harness_web_payload(self.runtime),
                },
            }
        )

    async def api_proactive_list(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        status = request.args.get("status", None)
        limit = request.args.get("limit", "10", type=str)
        limit_int = _safe_int(limit, 10, max_value=50)
        tasks = self.runtime.proactive_queue.list_tasks(
            scope, status=status, limit=limit_int
        )
        stats = self.runtime.proactive_queue.stats(scope)
        return jsonify({"ok": True, "tasks": tasks, "stats": stats})

    async def api_feedback_list(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = request.args.get("limit", "20", type=str)
        limit_int = _safe_int(limit, 20, max_value=50)
        items = self.runtime.feedback_queue.pending(scope, limit=limit_int)
        stats = self.runtime.feedback_queue.stats(scope)
        return jsonify({"ok": True, "items": items, "stats": stats})

    async def api_recall_gaps(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        status = request.args.get("status", "open")
        limit = request.args.get("limit", "20", type=str)
        result = self.runtime.memory_kernel.recall_gaps(
            scope,
            status,
            _safe_int(limit, 20, max_value=50),
        )
        return jsonify({"ok": True, **result})

    async def api_recall_gap_propose(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        result = self.runtime.memory_kernel.propose_recall_gap_memory(
            str(payload.get("scope", "global") or "global"),
            payload.get("gap_id", 0),
            str(payload.get("content", "") or ""),
            kind=str(payload.get("kind", "semantic_note") or "semantic_note"),
            user_id=str(payload.get("user_id", "") or ""),
        )
        status = 200 if result.get("queued") else 400
        if result.get("error") == "not_found":
            status = 404
        return jsonify({"ok": bool(result.get("queued")), "result": result}), status

    async def api_feedback_process(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        result = self.runtime.memory_kernel.process_memory_feedback(
            str(payload.get("scope", "global") or "global"),
            limit=_safe_int(payload.get("limit", 20), 20, max_value=50),
            actor="web",
        )
        return jsonify({"ok": True, **result})

    async def api_feedback_update(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        feedback_id = _safe_int(
            payload.get("feedback_id", 0),
            0,
            min_value=0,
            max_value=2_147_483_647,
        )
        if feedback_id <= 0:
            return jsonify({"ok": False, "error": "missing_feedback_id"}), 400
        result = self.runtime.feedback_queue.update_pending(
            self.runtime.storage,
            str(payload.get("scope", "global") or "global"),
            feedback_id,
            content=str(payload.get("content", "") or ""),
            memory_kind=str(payload.get("memory_kind", "") or ""),
            actor="web",
        )
        status = 200 if result.get("ok") else 400
        if result.get("error") == "not_found":
            status = 404
        return jsonify(result), status

    async def api_feedback_process_item(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        result = self.runtime.memory_kernel.process_memory_feedback_item(
            str(payload.get("scope", "global") or "global"),
            payload.get("feedback_id", 0),
            actor="web",
        )
        status = 200 if result.get("ok") else 400
        if result.get("error") == "not_found":
            status = 404
        return jsonify(result), status

    async def api_feedback_dismiss(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        feedback_id = _safe_int(
            payload.get("feedback_id", 0),
            0,
            min_value=0,
            max_value=2_147_483_647,
        )
        if feedback_id <= 0:
            return jsonify({"ok": False, "error": "missing_feedback_id"}), 400
        result = self.runtime.feedback_queue.dismiss_pending(
            self.runtime.storage,
            str(payload.get("scope", "global") or "global"),
            feedback_id,
            actor="web",
        )
        status = 200 if result.get("ok") else 404
        return jsonify(result), status
