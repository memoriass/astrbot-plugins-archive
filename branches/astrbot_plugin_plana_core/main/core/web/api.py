"""JSON API endpoint handlers for Plana Core web dashboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from quart import jsonify, make_response, request

from .inspectors import (
    build_bridge_status_payload,
    build_context_preview_payload,
    build_maintenance_status_payload,
    build_profile_payload,
    build_retrieve_test_payload,
)
from .page import dashboard_html

if TYPE_CHECKING:
    from ..runtime import PlanaRuntime


class PlanaWebAPI:
    """Thin handler layer exposing PlanaRuntime data as JSON endpoints."""

    def __init__(
        self,
        runtime: PlanaRuntime,
        debug_token: str = "",
        provider_getter: Callable[[], object | None] | None = None,
    ):
        self.runtime = runtime
        self.debug_token = debug_token
        self.provider_getter = provider_getter

    # ------------------------------------------------------------------
    # GET /plana/dashboard — serve HTML SPA
    # ------------------------------------------------------------------

    async def serve_dashboard(self):
        api_base = "/api/plug/plana"
        resp = await make_response(dashboard_html(api_base))
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    # ------------------------------------------------------------------
    # Auth helper
    # ------------------------------------------------------------------

    def _authorized(self) -> bool:
        if not self.debug_token:
            return True
        token = request.headers.get("X-Plana-Token", "").strip()
        if not token:
            token = (
                request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            )
        if not token:
            token = request.args.get("token", "").strip()
        return token == self.debug_token

    # ------------------------------------------------------------------
    # GET /plana/api/overview
    # ------------------------------------------------------------------

    async def api_overview(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        state = self.runtime.storage.get_state("global", self.runtime.mode)
        tables = self.runtime.storage.table_counts()
        cn = self.runtime.concept_graph.storage.count_nodes()
        ce = self.runtime.concept_graph.storage.count_edges()
        return jsonify(
            {
                "ok": True,
                "data": {
                    "enabled": self.runtime.enabled,
                    "mode": state.mode,
                    "focus": round(state.focus, 2),
                    "pressure": round(state.pressure, 2),
                    "risk_level": state.risk_level,
                    "concept_nodes": cn,
                    "concept_edges": ce,
                    "tables": tables,
                    "features": {
                        "memory_activation": self.runtime.enable_memory_activation,
                        "memory_consolidation": self.runtime.enable_memory_consolidation,
                        "memory_decay": self.runtime.enable_memory_decay,
                        "relation_graph": self.runtime.enable_relation_graph,
                        "concept_extraction": self.runtime.enable_concept_extraction,
                        "structured_memory_extraction": self.runtime.enable_structured_memory_extraction,
                        "memory_query_planner": self.runtime.enable_memory_query_planner,
                        "recall_tool": self.runtime.enable_recall_tool,
                        "recall_engine": self.runtime.debug_status_payload()[
                            "recall_engine"
                        ],
                        "memory_kinds": list(
                            self.runtime.debug_status_payload()["memory_kinds"]
                        ),
                        "task_queue": self.runtime.enable_task_queue,
                    },
                },
            }
        )

    # ------------------------------------------------------------------
    # GET /plana/api/memories?scope=global&limit=20&q=
    # ------------------------------------------------------------------

    async def api_memories(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = min(int(request.args.get("limit", "20")), 100)
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "").strip()
        if kind and query:
            results = self.runtime.storage.search_memories_by_kind(
                scope, query, kind, limit
            )
        elif kind:
            results = self.runtime.storage.recent_memories_by_kind(scope, kind, limit)
        elif query:
            results = self.runtime.storage.search_memories(scope, query, limit)
        else:
            results = self.runtime.storage.recent_memories(scope, limit)
        items = [
            {
                "id": m.id,
                "kind": m.kind,
                "content": m.content,
                "importance": round(m.importance, 3),
                "source": m.source,
                "created_at": m.created_at,
            }
            for m in results
        ]
        return jsonify({"ok": True, "data": items})

    async def api_retrieve_test(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "").strip()
        limit = min(int(request.args.get("limit", "8")), 50)
        data = build_retrieve_test_payload(self.runtime, scope, query, kind, limit)
        return jsonify({"ok": True, "data": data})

    async def api_profile(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = min(int(request.args.get("limit", "20")), 80)
        data = build_profile_payload(self.runtime, scope, limit)
        return jsonify({"ok": True, "data": data})

    async def api_bridge_status(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "data": build_bridge_status_payload(self.runtime)})

    async def api_context_preview(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "").strip()
        limit = min(int(request.args.get("limit", "8")), 50)
        data = build_context_preview_payload(self.runtime, scope, query, kind, limit)
        return jsonify({"ok": True, "data": data})

    async def api_maintenance_status(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify(
            {"ok": True, "data": build_maintenance_status_payload(self.runtime)}
        )

    async def api_maintenance_backup(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        body = await request.get_json(silent=True) or {}
        reason = str(body.get("reason", "manual"))
        result = self.runtime.maintenance.backup(reason)
        return jsonify({"ok": bool(result.get("ok")), "data": result})

    async def api_maintenance_rebuild_indexes(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        backup = self.runtime.maintenance.backup("before-rebuild-indexes")
        result = self.runtime.maintenance.rebuild_indexes()
        return jsonify({"ok": True, "data": {"backup": backup, "rebuild": result}})

    # ------------------------------------------------------------------
    # GET /plana/api/concepts?limit=50
    # ------------------------------------------------------------------

    async def api_concepts(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = min(int(request.args.get("limit", "50")), 200)
        all_nodes = self.runtime.concept_graph.storage.load_all_nodes()
        nodes = all_nodes[:limit]
        edges = self.runtime.concept_graph.storage.load_all_edges()
        node_data = [
            {
                "id": n.id,
                "concept": n.concept,
                "weight": round(n.weight, 2),
                "memory_items": n.memory_items,
                "created_at": n.created_at,
                "last_modified": n.last_modified,
            }
            for n in nodes
        ]
        edge_data = [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "strength": e.strength,
                "created_at": e.created_at,
                "last_modified": e.last_modified,
            }
            for e in edges
        ]
        return jsonify(
            {
                "ok": True,
                "data": {
                    "nodes": node_data,
                    "edges": edge_data,
                    "total_nodes": len(all_nodes),
                    "total_edges": len(edges),
                },
            }
        )

    # ------------------------------------------------------------------
    # GET /plana/api/relations?node=&limit=20
    # ------------------------------------------------------------------

    async def api_relations(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        node = request.args.get("node", "").strip()
        limit = min(int(request.args.get("limit", "20")), 100)
        if node:
            edges = self.runtime.storage.related_edges(node, limit)
        else:
            edges = self.runtime.storage.related_edges("", limit)
        items = [
            {
                "id": e.id,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "relation_type": e.relation_type,
                "weight": round(e.weight, 3),
                "confidence": round(e.confidence, 3),
                "evidence": e.evidence,
                "updated_at": e.updated_at,
            }
            for e in edges
        ]
        return jsonify({"ok": True, "data": items})

    # ------------------------------------------------------------------
    # GET /plana/api/tasks?scope=global&limit=20
    # ------------------------------------------------------------------

    async def api_tasks(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = min(int(request.args.get("limit", "20")), 100)
        tasks = self.runtime.storage.list_tasks(scope, limit)
        items = [
            {
                "id": t.id,
                "objective": t.objective,
                "status": t.status,
                "risk_level": t.risk_level,
                "owner_id": t.owner_id,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tasks
        ]
        return jsonify({"ok": True, "data": items})

    # ------------------------------------------------------------------
    # POST /plana/api/maintain — trigger maintenance manually
    # ------------------------------------------------------------------

    async def api_maintain(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        results: dict[str, object] = {
            "consolidate": None,
            "decay": None,
            "accumulate": None,
        }
        if self.runtime.enable_memory_consolidation:
            report = self.runtime.memory_consolidator.consolidate_scope("global", None)
            results["consolidate"] = {
                "processed": report.processed,
                "skipped": report.skipped,
                "semantic_written": report.semantic_written,
            }
        if self.runtime.enable_memory_decay:
            report = self.runtime.memory_decay.decay_scope("global")
            results["decay"] = {
                "processed": report.processed,
                "decayed": report.decayed,
                "skipped": report.skipped,
            }
        if self.runtime.enable_concept_extraction:
            provider = self.provider_getter() if self.provider_getter else None
            if provider is None:
                results["accumulate"] = {"skipped": "provider_unavailable"}
            else:
                results["accumulate"] = await self.runtime.auto_accumulate_concepts(
                    "global", provider
                )
        return jsonify({"ok": True, "data": results})

    # ------------------------------------------------------------------
    # DELETE /plana/api/memory/<id> — delete episodic memory
    # ------------------------------------------------------------------

    async def api_delete_memory(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        memory_id = payload.get("id")
        confirm = payload.get("confirm", False)
        if not memory_id:
            return jsonify({"ok": False, "error": "missing_id"}), 400
        if not confirm:
            return jsonify(
                {"ok": False, "error": "confirmation_required", "id": memory_id}
            ), 400
        result = self.runtime.memory_storage.delete_memory(int(memory_id), actor="web")
        return jsonify(result)

    # ------------------------------------------------------------------
    # DELETE /plana/api/semantic/<id> — delete semantic memory
    # ------------------------------------------------------------------

    async def api_delete_semantic(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        semantic_id = payload.get("id")
        confirm = payload.get("confirm", False)
        if not semantic_id:
            return jsonify({"ok": False, "error": "missing_id"}), 400
        if not confirm:
            return jsonify(
                {"ok": False, "error": "confirmation_required", "id": semantic_id}
            ), 400
        result = self.runtime.memory_storage.delete_semantic(
            int(semantic_id), actor="web"
        )
        return jsonify(result)

    # ------------------------------------------------------------------
    # POST /plana/api/clean-orphans — remove orphan links/decay/edges
    # ------------------------------------------------------------------

    async def api_clean_orphans(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            payload = {}
        confirm = payload.get("confirm", False)
        if not confirm:
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        result = self.runtime.maintenance.clean_orphans(actor="web")
        return jsonify(result)

    # ------------------------------------------------------------------
    # GET /plana/api/audit — recent audit events
    # ------------------------------------------------------------------

    async def api_audit(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = request.args.get("limit", "20", type=str)
        try:
            limit_int = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            limit_int = 20
        events = self.runtime.memory_storage.audit.recent(limit_int)
        return jsonify({"ok": True, "data": events, "count": len(events)})

    # ------------------------------------------------------------------
    # GET /plana/api/proactive — list proactive tasks
    # ------------------------------------------------------------------

    async def api_proactive_list(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        status = request.args.get("status", None)
        limit = request.args.get("limit", "10", type=str)
        try:
            limit_int = max(1, min(int(limit), 50))
        except (TypeError, ValueError):
            limit_int = 10
        tasks = self.runtime.proactive_queue.list_tasks(
            scope, status=status, limit=limit_int
        )
        stats = self.runtime.proactive_queue.stats(scope)
        return jsonify({"ok": True, "tasks": tasks, "stats": stats})

    # ------------------------------------------------------------------
    # POST /plana/api/proactive/enqueue — add a proactive task
    # ------------------------------------------------------------------

    async def api_proactive_enqueue(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        scope = payload.get("scope", "global")
        kind = payload.get("kind", "")
        content = payload.get("payload", "")
        user_id = payload.get("user_id", "")
        priority = int(payload.get("priority", 0))
        delay = int(payload.get("delay_seconds", 0))
        ttl = payload.get("ttl_seconds")
        ttl_int = int(ttl) if ttl is not None else None
        task_id = self.runtime.proactive_queue.enqueue(
            scope,
            kind,
            content,
            user_id=user_id,
            priority=priority,
            delay_seconds=delay,
            ttl_seconds=ttl_int,
        )
        if task_id is None:
            return jsonify({"ok": False, "error": "invalid_kind"}), 400
        return jsonify({"ok": True, "task_id": task_id})

    # ------------------------------------------------------------------
    # POST /plana/api/proactive/poll — poll ready tasks
    # ------------------------------------------------------------------

    async def api_proactive_poll(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            payload = {}
        limit = int(payload.get("limit", 5))
        tasks = self.runtime.proactive_queue.poll_ready(limit=limit)
        return jsonify({"ok": True, "tasks": tasks})

    # ------------------------------------------------------------------
    # POST /plana/api/proactive/deliver — mark task delivered
    # ------------------------------------------------------------------

    async def api_proactive_deliver(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        task_id = payload.get("task_id")
        if not task_id:
            return jsonify({"ok": False, "error": "missing_task_id"}), 400
        ok = self.runtime.proactive_queue.mark_delivered(int(task_id))
        return jsonify({"ok": ok})

    # ------------------------------------------------------------------
    # POST /plana/api/proactive/cancel — cancel a task
    # ------------------------------------------------------------------

    async def api_proactive_cancel(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        task_id = payload.get("task_id")
        if not task_id:
            return jsonify({"ok": False, "error": "missing_task_id"}), 400
        ok = self.runtime.proactive_queue.cancel(int(task_id))
        return jsonify({"ok": ok})

    # ------------------------------------------------------------------
    # GET /plana/api/feedback — list pending feedback
    # ------------------------------------------------------------------

    async def api_feedback_list(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = request.args.get("limit", "20", type=str)
        try:
            limit_int = max(1, min(int(limit), 50))
        except (TypeError, ValueError):
            limit_int = 20
        items = self.runtime.feedback_queue.pending(scope, limit=limit_int)
        stats = self.runtime.feedback_queue.stats(scope)
        return jsonify({"ok": True, "items": items, "stats": stats})

    # ------------------------------------------------------------------
    # POST /plana/api/feedback/useful — mark memories as useful
    # ------------------------------------------------------------------

    async def api_feedback_useful(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        scope = payload.get("scope", "global")
        user_id = payload.get("user_id", "")
        memory_ids = payload.get("memory_ids", [])
        if not isinstance(memory_ids, list):
            return jsonify({"ok": False, "error": "invalid_memory_ids"}), 400
        fid = self.runtime.feedback_queue.submit_useful(scope, user_id, memory_ids)
        return jsonify({"ok": True, "feedback_id": fid})

    # ------------------------------------------------------------------
    # POST /plana/api/feedback/not-useful — mark memories as not useful
    # ------------------------------------------------------------------

    async def api_feedback_not_useful(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        scope = payload.get("scope", "global")
        user_id = payload.get("user_id", "")
        memory_ids = payload.get("memory_ids", [])
        reason = payload.get("reason", "")
        if not isinstance(memory_ids, list):
            return jsonify({"ok": False, "error": "invalid_memory_ids"}), 400
        fid = self.runtime.feedback_queue.submit_not_useful(
            scope, user_id, memory_ids, reason
        )
        return jsonify({"ok": True, "feedback_id": fid})

    # ------------------------------------------------------------------
    # POST /plana/api/feedback/new-memory — suggest new memory
    # ------------------------------------------------------------------

    async def api_feedback_new_memory(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        scope = payload.get("scope", "global")
        user_id = payload.get("user_id", "")
        content = payload.get("content", "")
        kind = payload.get("kind", "")
        fid = self.runtime.feedback_queue.submit_new_memory(
            scope, user_id, content, kind
        )
        if fid is None:
            return jsonify({"ok": False, "error": "empty_content"}), 400
        return jsonify({"ok": True, "feedback_id": fid})

    # ------------------------------------------------------------------
    # POST /plana/api/feedback/merge — suggest memory merge
    # ------------------------------------------------------------------

    async def api_feedback_merge(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        scope = payload.get("scope", "global")
        user_id = payload.get("user_id", "")
        memory_ids = payload.get("memory_ids", [])
        merged_content = payload.get("merged_content", "")
        if not isinstance(memory_ids, list) or len(memory_ids) < 2:
            return jsonify({"ok": False, "error": "need_at_least_2_ids"}), 400
        fid = self.runtime.feedback_queue.submit_merge(
            scope, user_id, memory_ids, merged_content
        )
        return jsonify({"ok": True, "feedback_id": fid})

    # ------------------------------------------------------------------
    # GET /plana/api/scope/aliases — list scope aliases
    # ------------------------------------------------------------------

    async def api_scope_aliases(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        canonical = request.args.get("canonical", None)
        aliases = self.runtime.scope_manager.list_aliases(canonical)
        return jsonify({"ok": True, "aliases": aliases})

    # ------------------------------------------------------------------
    # POST /plana/api/scope/alias — add scope alias
    # ------------------------------------------------------------------

    async def api_scope_add_alias(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        alias = payload.get("alias", "")
        canonical = payload.get("canonical", "")
        if not alias or not canonical:
            return jsonify({"ok": False, "error": "missing_alias_or_canonical"}), 400
        ok = self.runtime.scope_manager.add_alias(alias, canonical)
        return jsonify({"ok": ok})

    # ------------------------------------------------------------------
    # POST /plana/api/scope/remove-alias — remove scope alias
    # ------------------------------------------------------------------

    async def api_scope_remove_alias(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        alias = payload.get("alias", "")
        if not alias:
            return jsonify({"ok": False, "error": "missing_alias"}), 400
        ok = self.runtime.scope_manager.remove_alias(alias)
        return jsonify({"ok": ok})

    # ------------------------------------------------------------------
    # POST /plana/api/scope/migrate — migrate memories between scopes
    # ------------------------------------------------------------------

    async def api_scope_migrate(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        source = payload.get("source", "")
        target = payload.get("target", "")
        if not source or not target:
            return jsonify({"ok": False, "error": "missing_source_or_target"}), 400
        limit = int(payload.get("limit", 100))
        delete_source = bool(payload.get("delete_source", False))
        confirm = payload.get("confirm", False)
        if not confirm:
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        result = self.runtime.scope_manager.migrate_memories(
            source, target, limit=limit, delete_source=delete_source
        )
        return jsonify({"ok": True, **result})
