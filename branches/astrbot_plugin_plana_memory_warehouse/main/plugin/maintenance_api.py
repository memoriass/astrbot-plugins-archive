from __future__ import annotations

from quart import jsonify

from .config import bounded_int, prune_before_ts
from .http_api import contract_error, json_payload
from .store import CONTRACT_VERSION


class MemoryWarehouseMaintenanceApiMixin:
    async def _api_rebuild_index(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if not bool(payload.get("confirm", False)):
            return jsonify({"ok": False, "error": "confirm_required"}), 409
        return jsonify(self.store.rebuild_index())

    async def _api_prune(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        dry_run = bool(payload.get("dry_run", True))
        if not dry_run and not bool(payload.get("confirm", False)):
            return jsonify({"ok": False, "error": "confirm_required"}), 409
        before_ts = prune_before_ts(payload)
        if before_ts <= 0:
            return jsonify({"ok": False, "error": "invalid_prune_window"}), 400
        limit = bounded_int(payload.get("limit"), 1000, minimum=1, maximum=50_000)
        result = self.store.prune(before_ts=before_ts, limit=limit, dry_run=dry_run)
        return jsonify(result)

    async def _api_backup(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        if not bool(payload.get("confirm", False)):
            return jsonify({"ok": False, "error": "confirm_required"}), 409
        result = self.store.create_backup()
        return jsonify(result), 200 if result.get("ok") else 500

    async def _api_validate_backup(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        result = self.store.validate_backup(str(payload.get("backup_name") or ""))
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_restore_candidate(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        if not bool(payload.get("confirm", False)):
            return jsonify({"ok": False, "error": "confirm_required"}), 409
        result = self.store.prepare_restore_candidate(
            str(payload.get("backup_name") or "")
        )
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_delete_evidence(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        dry_run = bool(payload.get("dry_run", True))
        if not dry_run and not bool(payload.get("confirm", False)):
            return jsonify({"ok": False, "error": "confirm_required"}), 409
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        result = self.store.delete_evidence(
            request_id=str(payload.get("request_id") or ""),
            evidence_ids=[str(item) for item in evidence_ids],
            scope_id=str(payload.get("scope_id") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            dry_run=dry_run,
        )
        return jsonify(result), 200 if result.get("ok") else 400
