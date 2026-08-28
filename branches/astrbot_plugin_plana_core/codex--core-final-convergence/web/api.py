"""JSON API endpoint handlers for Plana Core web dashboard."""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import TYPE_CHECKING

from quart import g, jsonify, make_response, request

from .inspectors import (
    build_bridge_status_payload,
    build_context_preview_payload,
    build_maintenance_status_payload,
    build_profile_payload,
    build_retrieve_test_payload,
    memory_payload,
)
from .admin_api import PlanaWebAdminAPIMixin
from .auth import is_loopback_request
from .diagnostics_api import PlanaDiagnosticsAPIMixin
from .integration_payload import build_integration_web_payload
from .overview_payload import build_overview_payload
from .memory_scope_payload import build_memory_scope_payload
from .page import dashboard_html
from .remote_task_payload import ACTIVE_STATUSES, build_remote_task_web_payload
from .resource_payload import build_resource_web_payload

if TYPE_CHECKING:
    from ..plugin.runtime import PlanaRuntime

PLUGIN_PAGE_API_PREFIX = "/api/plug/astrbot_plugin_plana_core"


def _astrbot_dashboard_user() -> str:
    try:
        from astrbot.api.web import request as astrbot_request

        username = str(astrbot_request.username or "").strip()
    except Exception:  # noqa: BLE001
        username = ""
    if username:
        return username
    try:
        return str(getattr(g, "username", "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


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


class PlanaWebAPI(
    PlanaDiagnosticsAPIMixin,
    PlanaWebAdminAPIMixin,
):
    """Thin handler layer exposing PlanaRuntime data as JSON endpoints."""

    def __init__(
        self,
        runtime: PlanaRuntime,
        provider_getter: Callable[[], object | None] | None = None,
    ):
        self.runtime = runtime
        self.provider_getter = provider_getter

    async def serve_dashboard(self):
        if not self._authorized():
            resp = await make_response(
                "请从 AstrBot Dashboard 插件页进入，或使用本机回环地址调试。",
                401,
            )
            resp.headers["Content-Type"] = "text/plain; charset=utf-8"
            return resp
        bridge_mode = request.path.startswith(PLUGIN_PAGE_API_PREFIX)
        api_base = "/__plana_bridge_api__" if bridge_mode else "/api/plug/plana"
        resp = await make_response(dashboard_html(api_base, bridge_mode=bridge_mode))
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    def _authorized(self) -> bool:
        if _astrbot_dashboard_user():
            return True
        if is_loopback_request(request):
            return True
        return False

    def _dashboard_actor(self) -> str:
        return _astrbot_dashboard_user() or "web_dashboard"

    async def api_auth_info(self):
        astrbot_dashboard_user = bool(_astrbot_dashboard_user())
        loopback = is_loopback_request(request)
        return jsonify(
            {
                "auth_required": not (astrbot_dashboard_user or loopback),
                "loopback_access": loopback,
                "astrbot_dashboard_user": astrbot_dashboard_user,
                "auth_model": "astrbot_dashboard_or_loopback",
            }
        )

    async def api_overview(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "data": build_overview_payload(self.runtime)})

    async def api_resources(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = _safe_int(request.args.get("limit", "80"), 80, max_value=200)
        return jsonify({"ok": True, "data": await build_resource_web_payload(self.runtime, limit=limit)})

    async def api_integrations(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "data": await build_integration_web_payload(self.runtime)})

    async def api_webhook(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        service = getattr(self.runtime, "webhook_governance", None)
        if service is None:
            return jsonify({"ok": False, "error": "webhook_governance_unavailable"}), 503
        limit = _safe_int(request.args.get("limit", "50"), 50, max_value=200)
        return jsonify({
            "ok": True,
            "data": {
                "status": service.status(),
                "sources": service.sources().get("sources", []),
                "events": service.events(limit).get("events", []),
            },
        })

    async def api_webhook_policy(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if payload.get("confirm") is not True:
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        service = getattr(self.runtime, "webhook_governance", None)
        if service is None:
            return jsonify({"ok": False, "error": "webhook_governance_unavailable"}), 503
        result = service.update_policy(
            str(payload.get("source") or ""),
            payload,
            actor=self._dashboard_actor(),
        )
        return jsonify(result), 200 if result.get("ok") else 400

    async def api_webhook_replay(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if payload.get("confirm") is not True:
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        service = getattr(self.runtime, "webhook_governance", None)
        if service is None:
            return jsonify({"ok": False, "error": "webhook_governance_unavailable"}), 503
        result = await service.replay(str(payload.get("event_id") or ""))
        return jsonify(result), 200 if result.get("ok") else 409

    async def api_remote_tasks(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "").strip()
        limit = _safe_int(request.args.get("limit", "40"), 40, max_value=50)
        stats = self.runtime.remote_task_runs.stats()
        items = self.runtime.remote_task_runs.recent(scope_id=scope, limit=limit)
        return jsonify(
            {"ok": True, "data": build_remote_task_web_payload(stats, items)}
        )

    async def api_remote_task_cancel(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True) if request.content_length else {}
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not payload.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id:
            return jsonify({"ok": False, "error": "missing_request_id"}), 400
        run = self.runtime.remote_task_runs.get(request_id)
        if run is None:
            return jsonify({"ok": False, "error": "not_found"}), 404
        if str(run.get("status") or "") not in ACTIVE_STATUSES:
            return jsonify({"ok": False, "error": "remote_task_not_active"}), 409
        delegator = getattr(self.runtime, "remote_task_delegator", None)
        cancel = getattr(delegator, "cancel", None)
        if not callable(cancel):
            return jsonify({"ok": False, "error": "remote_cancel_unavailable"}), 503
        result = await cancel(run)
        status_code = 200 if result.ok else 409
        return jsonify({"ok": result.ok, "data": result.to_dict()}), status_code

    async def api_memories(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = _safe_int(request.args.get("limit", "20"), 20, max_value=100)
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "").strip()
        result = self.runtime.memory_kernel.search(scope, query, kind, limit)
        items = [
            memory_payload(
                item,
                self.runtime.memory_storage.atoms_for_memory(item.id),
            )
            for item in result["memories"]
        ]
        return jsonify({"ok": True, "data": items})

    async def api_memory_scopes(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = _safe_int(request.args.get("limit", "160"), 160, max_value=200)
        return jsonify({"ok": True, "data": build_memory_scope_payload(self.runtime, limit)})

    async def api_retrieve_test(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        query = request.args.get("q", "").strip()
        kind = request.args.get("kind", "").strip()
        limit = _safe_int(request.args.get("limit", "8"), 8, max_value=50)
        data = build_retrieve_test_payload(self.runtime, scope, query, kind, limit)
        return jsonify({"ok": True, "data": data})

    async def api_profile(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        scope = request.args.get("scope", "global")
        limit = _safe_int(request.args.get("limit", "20"), 20, max_value=80)
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
        limit = _safe_int(request.args.get("limit", "8"), 8, max_value=50)
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
        if not isinstance(body, dict):
            body = {}
        if not body.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        reason = str(body.get("reason", "manual"))
        result = self.runtime.maintenance.backup(reason)
        return jsonify({"ok": bool(result.get("ok")), "data": result})

    async def api_maintenance_rebuild_indexes(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        body = await request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        if not body.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        backup = self.runtime.maintenance.backup("before-rebuild-indexes")
        result = self.runtime.maintenance.rebuild_indexes()
        return jsonify({"ok": True, "data": {"backup": backup, "rebuild": result}})

    async def api_concepts(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = _safe_int(request.args.get("limit", "50"), 50, max_value=200)
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

    async def api_relations(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        node = request.args.get("node", "").strip()
        scope = request.args.get("scope", "global").strip() or "global"
        limit = _safe_int(request.args.get("limit", "20"), 20, max_value=100)
        if node:
            edges = self.runtime.storage.related_edges(node, limit, scope)
        else:
            edges = self.runtime.storage.related_edges("", limit, scope)
        items = [
            {
                "id": e.id,
                "scope_id": e.scope_id,
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

    async def api_tasks(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        limit = _safe_int(request.args.get("limit", "20"), 20, max_value=100)
        sessions = getattr(self.runtime, "assistant_task_sessions", None)
        traces = sessions.recent_traces(limit) if sessions is not None else []
        items = [
            {
                "id": f"trace-{index}",
                "title": str(item.get("text") or item.get("capability") or "会话任务"),
                "content": str(item.get("reason") or item.get("recovery") or ""),
                "status": str(item.get("status") or "observed"),
                "source": str(item.get("route") or "task_session"),
                "capability": str(item.get("capability") or ""),
                "created_at": item.get("created_at"),
                "updated_at": item.get("created_at"),
            }
            for index, item in enumerate(traces, start=1)
        ]
        return jsonify({"ok": True, "data": items})

    async def api_maintain(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        body = await request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        if not body.get("confirm", False):
            return jsonify({"ok": False, "error": "confirmation_required"}), 400
        results: dict[str, object] = {
            "consolidate": None,
            "decay": None,
            "accumulate": None,
            "scopes": {},
        }
        pushed = 0
        failed = 0
        last_error = ""
        detail_rows: list[dict[str, object]] = []
        provider = self.provider_getter() if self.provider_getter else None
        for scope_id in self._memory_maintenance_scopes():
            try:
                scope_result = await self.runtime.memory_kernel.maintain(
                    scope_id,
                provider if scope_id == "global" else None,
                consolidate=True,
                decay=True,
                accumulate=(
                    scope_id == "global"
                    and self.runtime.enable_concept_extraction
                ),
                push_warehouse=True,
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                last_error = str(exc)[:160]
                scope_result = {
                    "scope": scope_id,
                    "error": "maintain_failed",
                    "detail": str(exc)[:200],
                }
            warehouse = scope_result.get("warehouse")
            if isinstance(warehouse, dict) and warehouse.get("ok"):
                pushed += 1
            elif isinstance(warehouse, dict) and warehouse.get("error"):
                last_error = str(warehouse.get("error") or "")[:160]
            detail_rows.append(
                {
                    "scope": scope_id,
                    "ok": "error" not in scope_result,
                    "consolidate": scope_result.get("consolidate", {}),
                    "decay": scope_result.get("decay", {}),
                    "warehouse": warehouse if isinstance(warehouse, dict) else {},
                }
            )
            scopes = results["scopes"]
            if isinstance(scopes, dict):
                scopes[scope_id] = scope_result
            if scope_id == "global":
                results["consolidate"] = scope_result.get("consolidate")
                results["decay"] = scope_result.get("decay")
                results["accumulate"] = scope_result.get("accumulate")
        self.runtime.memory_maintenance_last_run = {
            "ran_at": int(time.time()),
            "scope_count": len(detail_rows),
            "warehouse_pushed": pushed,
            "failed": failed,
            "last_error": last_error,
            "scopes": detail_rows[:20],
            "trigger": "web_manual",
        }
        return jsonify({"ok": True, "data": results})

    def _memory_maintenance_scopes(self) -> list[str]:
        scopes = ["global"]
        active_scopes = getattr(self.runtime.storage, "active_memory_scopes", None)
        if callable(active_scopes):
            try:
                scopes.extend(active_scopes(12, since_ts=int(time.time()) - 30 * 86400))
            except Exception:  # noqa: BLE001
                pass
        seen: set[str] = set()
        result: list[str] = []
        for scope_id in scopes:
            scope = str(scope_id or "global").strip()[:200]
            if not scope or scope in seen:
                continue
            seen.add(scope)
            result.append(scope)
        return result
