"""Plana Core 独立 Web 管理服务器（FastAPI + Uvicorn）。

独立运行于 AstrBot 主 Quart 服务之外，提供：
- Bearer Token 认证（secrets.compare_digest 防时序攻击）
- 全量 REST API（overview / memories / concepts / relations / tasks / maintain / config）
- WebSocket 实时推送 (/ws)
- 定时 token 清理
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from .inspectors import (
    build_bridge_status_payload,
    build_context_preview_payload,
    build_maintenance_status_payload,
    build_profile_payload,
    build_retrieve_test_payload,
)

if TYPE_CHECKING:
    from ..runtime import PlanaRuntime

try:
    import uvicorn
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    from .page import dashboard_html

    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False
    logger.warning(
        "[Plana] FastAPI/Uvicorn 未安装，独立 Web 管理端不可用。pip install fastapi uvicorn"
    )


class PlanaWebServer:
    """Plana Core 独立端口 Web 管理服务器。"""

    _TOKEN_EXPIRE = 86400  # 24 小时

    def __init__(
        self,
        runtime: PlanaRuntime,
        config: dict[str, Any],
        provider_getter: Callable[[], object | None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config
        self.provider_getter = provider_getter
        self.app: Any | None = None
        self._server: Any | None = None
        self._server_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._ws_connections: list[Any] = []
        self._tokens: dict[str, float] = {}
        self._auth_enabled = bool(self._web_admin().get("password", ""))
        if _FASTAPI_OK:
            self._build_app()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _web_admin(self) -> dict[str, Any]:
        return self.config.get("web_admin", {}) or {}

    def _issue_token(self) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = time.time() + self._TOKEN_EXPIRE
        return token

    def _verify_token(self, token: str) -> bool:
        if not token:
            return False
        if token == "no-auth":
            return not self._auth_enabled
        expire_at = self._tokens.get(token)
        if not expire_at:
            return False
        if time.time() > expire_at:
            self._tokens.pop(token, None)
            return False
        return True

    def _get_bearer(self, request: Any) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return request.query_params.get("token", "")

    # ------------------------------------------------------------------
    # 构建 FastAPI 应用
    # ------------------------------------------------------------------

    def _build_app(self) -> None:
        self.app = FastAPI(title="Plana Core Dashboard", version="1.0")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @self.app.middleware("http")
        async def _auth_mw(request: Request, call_next):  # type: ignore[misc]
            if not self._auth_enabled:
                return await call_next(request)
            path = request.url.path
            if path in {"/api/login", "/api/auth-info"}:
                return await call_next(request)
            if not path.startswith("/api"):
                return await call_next(request)
            if not self._verify_token(self._get_bearer(request)):
                return JSONResponse({"error": "未授权"}, status_code=401)
            return await call_next(request)

        self._register_routes()

    def _register_routes(self) -> None:
        app = self.app

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return HTMLResponse(dashboard_html(""))

        @app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard():
            return HTMLResponse(dashboard_html(""))

        @app.get("/api/auth-info")
        async def auth_info():
            return {"auth_required": self._auth_enabled}

        @app.post("/api/login")
        async def login(body: dict[str, Any]):
            pwd = self._web_admin().get("password", "")
            if not pwd:
                return {"token": "no-auth", "auth_required": False}
            inp = str(body.get("password", ""))
            if not secrets.compare_digest(inp, pwd):
                return JSONResponse({"error": "密码错误"}, status_code=401)
            return {"token": self._issue_token(), "auth_required": True}

        @app.get("/api/overview")
        async def overview():
            rt = self.runtime
            state = rt.storage.get_state("global", rt.mode)
            tables = rt.storage.table_counts()
            return {
                "ok": True,
                "data": {
                    "enabled": rt.enabled,
                    "mode": state.mode,
                    "focus": round(state.focus, 2),
                    "pressure": round(state.pressure, 2),
                    "risk_level": state.risk_level,
                    "concept_nodes": rt.concept_graph.storage.count_nodes(),
                    "concept_edges": rt.concept_graph.storage.count_edges(),
                    "tables": tables,
                    "features": {
                        "memory_activation": rt.enable_memory_activation,
                        "memory_consolidation": rt.enable_memory_consolidation,
                        "memory_decay": rt.enable_memory_decay,
                        "relation_graph": rt.enable_relation_graph,
                        "concept_extraction": rt.enable_concept_extraction,
                        "structured_memory_extraction": rt.enable_structured_memory_extraction,
                        "memory_query_planner": rt.enable_memory_query_planner,
                        "recall_tool": rt.enable_recall_tool,
                        "recall_engine": rt.debug_status_payload()["recall_engine"],
                        "memory_kinds": list(rt.debug_status_payload()["memory_kinds"]),
                        "task_queue": rt.enable_task_queue,
                    },
                },
            }

        @app.get("/api/memories")
        async def memories(
            scope: str = "global",
            limit: int = 20,
            q: str = "",
            kind: str = "",
        ):
            limit = min(limit, 100)
            rt = self.runtime
            if kind and q:
                items_raw = rt.storage.search_memories_by_kind(scope, q, kind, limit)
            elif kind:
                items_raw = rt.storage.recent_memories_by_kind(scope, kind, limit)
            elif q:
                items_raw = rt.storage.search_memories(scope, q, limit)
            else:
                items_raw = rt.storage.recent_memories(scope, limit)
            return {
                "ok": True,
                "data": [
                    {
                        "id": m.id,
                        "kind": m.kind,
                        "content": m.content,
                        "importance": round(m.importance, 3),
                        "source": m.source,
                        "created_at": m.created_at,
                    }
                    for m in items_raw
                ],
            }

        @app.get("/api/retrieve-test")
        async def retrieve_test(
            scope: str = "global",
            q: str = "",
            kind: str = "",
            limit: int = 8,
        ):
            return {
                "ok": True,
                "data": build_retrieve_test_payload(
                    self.runtime, scope, q.strip(), kind.strip(), min(limit, 50)
                ),
            }

        @app.get("/api/profile")
        async def profile(scope: str = "global", limit: int = 20):
            return {
                "ok": True,
                "data": build_profile_payload(self.runtime, scope, min(limit, 80)),
            }

        @app.get("/api/bridge-status")
        async def bridge_status():
            return {"ok": True, "data": build_bridge_status_payload(self.runtime)}

        @app.get("/api/context-preview")
        async def context_preview(
            scope: str = "global",
            q: str = "",
            kind: str = "",
            limit: int = 8,
        ):
            return {
                "ok": True,
                "data": build_context_preview_payload(
                    self.runtime, scope, q.strip(), kind.strip(), min(limit, 50)
                ),
            }

        @app.get("/api/concepts")
        async def concepts(limit: int = 50):
            limit = min(limit, 200)
            rt = self.runtime
            all_nodes = rt.concept_graph.storage.load_all_nodes()
            edges = rt.concept_graph.storage.load_all_edges()
            return {
                "ok": True,
                "data": {
                    "nodes": [
                        {
                            "id": n.id,
                            "concept": n.concept,
                            "weight": round(n.weight, 2),
                            "memory_items": n.memory_items,
                            "created_at": n.created_at,
                            "last_modified": n.last_modified,
                        }
                        for n in all_nodes[:limit]
                    ],
                    "edges": [
                        {
                            "id": e.id,
                            "source": e.source,
                            "target": e.target,
                            "strength": e.strength,
                            "created_at": e.created_at,
                            "last_modified": e.last_modified,
                        }
                        for e in edges
                    ],
                    "total_nodes": len(all_nodes),
                    "total_edges": len(edges),
                },
            }

        @app.get("/api/relations")
        async def relations(node: str = "", limit: int = 20):
            limit = min(limit, 100)
            edges = self.runtime.storage.related_edges(node, limit)
            return {
                "ok": True,
                "data": [
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
                ],
            }

        @app.get("/api/tasks")
        async def tasks(scope: str = "global", limit: int = 20):
            limit = min(limit, 100)
            items = self.runtime.storage.list_tasks(scope, limit)
            return {
                "ok": True,
                "data": [
                    {
                        "id": t.id,
                        "objective": t.objective,
                        "status": t.status,
                        "risk_level": t.risk_level,
                        "owner_id": t.owner_id,
                        "created_at": t.created_at,
                        "updated_at": t.updated_at,
                    }
                    for t in items
                ],
            }

        @app.get("/api/maintenance-status")
        async def maintenance_status():
            return {
                "ok": True,
                "data": build_maintenance_status_payload(self.runtime),
            }

        @app.post("/api/backup")
        async def backup(body: dict[str, Any] | None = None):
            reason = "manual"
            if body:
                reason = str(body.get("reason", "manual"))
            result = self.runtime.maintenance.backup(reason)
            return {"ok": bool(result.get("ok")), "data": result}

        @app.post("/api/rebuild-indexes")
        async def rebuild_indexes():
            backup_result = self.runtime.maintenance.backup("before-rebuild-indexes")
            rebuild_result = self.runtime.maintenance.rebuild_indexes()
            return {
                "ok": True,
                "data": {"backup": backup_result, "rebuild": rebuild_result},
            }

        @app.post("/api/maintain")
        async def maintain():
            rt = self.runtime
            results: dict[str, Any] = {
                "consolidate": None,
                "decay": None,
                "accumulate": None,
            }
            if rt.enable_memory_consolidation:
                rep = rt.memory_consolidator.consolidate_scope("global", None)
                results["consolidate"] = {
                    "processed": rep.processed,
                    "skipped": rep.skipped,
                    "semantic_written": rep.semantic_written,
                }
            if rt.enable_memory_decay:
                rep = rt.memory_decay.decay_scope("global")
                results["decay"] = {
                    "processed": rep.processed,
                    "decayed": rep.decayed,
                    "skipped": rep.skipped,
                }
            if rt.enable_concept_extraction:
                provider = self.provider_getter() if self.provider_getter else None
                if provider is None:
                    results["accumulate"] = {"skipped": "provider_unavailable"}
                else:
                    results["accumulate"] = await rt.auto_accumulate_concepts(
                        "global", provider
                    )

            return {"ok": True, "data": results}

        @app.post("/api/delete-memory")
        async def delete_memory(body: dict[str, Any]):
            memory_id = body.get("id")
            confirm = body.get("confirm", False)
            if not memory_id:
                return JSONResponse(
                    {"ok": False, "error": "missing_id"}, status_code=400
                )
            if not confirm:
                return JSONResponse(
                    {"ok": False, "error": "confirmation_required", "id": memory_id},
                    status_code=400,
                )
            return self.runtime.memory_storage.delete_memory(
                int(memory_id), actor="web"
            )

        @app.post("/api/delete-semantic")
        async def delete_semantic(body: dict[str, Any]):
            semantic_id = body.get("id")
            confirm = body.get("confirm", False)
            if not semantic_id:
                return JSONResponse(
                    {"ok": False, "error": "missing_id"}, status_code=400
                )
            if not confirm:
                return JSONResponse(
                    {"ok": False, "error": "confirmation_required", "id": semantic_id},
                    status_code=400,
                )
            return self.runtime.memory_storage.delete_semantic(
                int(semantic_id), actor="web"
            )

        @app.post("/api/clean-orphans")
        async def clean_orphans(body: dict[str, Any] | None = None):
            if not body or not body.get("confirm", False):
                return JSONResponse(
                    {"ok": False, "error": "confirmation_required"}, status_code=400
                )
            return self.runtime.maintenance.clean_orphans(actor="web")

        @app.get("/api/audit")
        async def audit(limit: int = 20):
            limit = max(1, min(limit, 100))
            events = self.runtime.memory_storage.audit.recent(limit)
            return {"ok": True, "data": events, "count": len(events)}

        @app.get("/api/proactive")
        async def proactive_list(
            scope: str = "global", status: str | None = None, limit: int = 10
        ):
            limit = max(1, min(limit, 50))
            tasks = self.runtime.proactive_queue.list_tasks(
                scope, status=status, limit=limit
            )
            stats = self.runtime.proactive_queue.stats(scope)
            return {"ok": True, "tasks": tasks, "stats": stats}

        @app.post("/api/proactive/enqueue")
        async def proactive_enqueue(body: dict[str, Any]):
            scope = body.get("scope", "global")
            kind = body.get("kind", "")
            content = body.get("payload", "")
            user_id = body.get("user_id", "")
            priority = int(body.get("priority", 0))
            delay = int(body.get("delay_seconds", 0))
            ttl = body.get("ttl_seconds")
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
                return JSONResponse(
                    {"ok": False, "error": "invalid_kind"}, status_code=400
                )
            return {"ok": True, "task_id": task_id}

        @app.post("/api/proactive/poll")
        async def proactive_poll(body: dict[str, Any] | None = None):
            limit = int((body or {}).get("limit", 5))
            tasks = self.runtime.proactive_queue.poll_ready(limit=limit)
            return {"ok": True, "tasks": tasks}

        @app.post("/api/proactive/deliver")
        async def proactive_deliver(body: dict[str, Any]):
            task_id = body.get("task_id")
            if not task_id:
                return JSONResponse(
                    {"ok": False, "error": "missing_task_id"}, status_code=400
                )
            ok = self.runtime.proactive_queue.mark_delivered(int(task_id))
            return {"ok": ok}

        @app.post("/api/proactive/cancel")
        async def proactive_cancel(body: dict[str, Any]):
            task_id = body.get("task_id")
            if not task_id:
                return JSONResponse(
                    {"ok": False, "error": "missing_task_id"}, status_code=400
                )
            ok = self.runtime.proactive_queue.cancel(int(task_id))
            return {"ok": ok}

        @app.get("/api/feedback")
        async def feedback_list(scope: str = "global", limit: int = 20):
            limit = max(1, min(limit, 50))
            items = self.runtime.feedback_queue.pending(scope, limit=limit)
            stats = self.runtime.feedback_queue.stats(scope)
            return {"ok": True, "items": items, "stats": stats}

        @app.post("/api/feedback/useful")
        async def feedback_useful(body: dict[str, Any]):
            scope = body.get("scope", "global")
            user_id = body.get("user_id", "")
            memory_ids = body.get("memory_ids", [])
            if not isinstance(memory_ids, list):
                return JSONResponse(
                    {"ok": False, "error": "invalid_memory_ids"}, status_code=400
                )
            fid = self.runtime.feedback_queue.submit_useful(scope, user_id, memory_ids)
            return {"ok": True, "feedback_id": fid}

        @app.post("/api/feedback/not-useful")
        async def feedback_not_useful(body: dict[str, Any]):
            scope = body.get("scope", "global")
            user_id = body.get("user_id", "")
            memory_ids = body.get("memory_ids", [])
            reason = body.get("reason", "")
            if not isinstance(memory_ids, list):
                return JSONResponse(
                    {"ok": False, "error": "invalid_memory_ids"}, status_code=400
                )
            fid = self.runtime.feedback_queue.submit_not_useful(
                scope, user_id, memory_ids, reason
            )
            return {"ok": True, "feedback_id": fid}

        @app.post("/api/feedback/new-memory")
        async def feedback_new_memory(body: dict[str, Any]):
            scope = body.get("scope", "global")
            user_id = body.get("user_id", "")
            content = body.get("content", "")
            kind = body.get("kind", "")
            fid = self.runtime.feedback_queue.submit_new_memory(
                scope, user_id, content, kind
            )
            if fid is None:
                return JSONResponse(
                    {"ok": False, "error": "empty_content"}, status_code=400
                )
            return {"ok": True, "feedback_id": fid}

        @app.post("/api/feedback/merge")
        async def feedback_merge(body: dict[str, Any]):
            scope = body.get("scope", "global")
            user_id = body.get("user_id", "")
            memory_ids = body.get("memory_ids", [])
            merged_content = body.get("merged_content", "")
            if not isinstance(memory_ids, list) or len(memory_ids) < 2:
                return JSONResponse(
                    {"ok": False, "error": "need_at_least_2_ids"}, status_code=400
                )
            fid = self.runtime.feedback_queue.submit_merge(
                scope, user_id, memory_ids, merged_content
            )
            return {"ok": True, "feedback_id": fid}

        @app.get("/api/scope/aliases")
        async def scope_aliases(canonical: str | None = None):
            aliases = self.runtime.scope_manager.list_aliases(canonical)
            return {"ok": True, "aliases": aliases}

        @app.post("/api/scope/alias")
        async def scope_add_alias(body: dict[str, Any]):
            alias = body.get("alias", "")
            canonical = body.get("canonical", "")
            if not alias or not canonical:
                return JSONResponse(
                    {"ok": False, "error": "missing_alias_or_canonical"},
                    status_code=400,
                )
            ok = self.runtime.scope_manager.add_alias(alias, canonical)
            return {"ok": ok}

        @app.post("/api/scope/remove-alias")
        async def scope_remove_alias(body: dict[str, Any]):
            alias = body.get("alias", "")
            if not alias:
                return JSONResponse(
                    {"ok": False, "error": "missing_alias"}, status_code=400
                )
            ok = self.runtime.scope_manager.remove_alias(alias)
            return {"ok": ok}

        @app.post("/api/scope/migrate")
        async def scope_migrate(body: dict[str, Any]):
            source = body.get("source", "")
            target = body.get("target", "")
            if not source or not target:
                return JSONResponse(
                    {"ok": False, "error": "missing_source_or_target"},
                    status_code=400,
                )
            confirm = body.get("confirm", False)
            if not confirm:
                return JSONResponse(
                    {"ok": False, "error": "confirmation_required"}, status_code=400
                )
            limit = int(body.get("limit", 100))
            delete_source = bool(body.get("delete_source", False))
            result = self.runtime.scope_manager.migrate_memories(
                source, target, limit=limit, delete_source=delete_source
            )
            return {"ok": True, **result}

        @app.get("/api/config")
        async def get_config():
            wa = {k: v for k, v in self._web_admin().items() if k != "password"}
            return {"ok": True, "data": {"web_admin": wa}}

        @app.get("/api/config-schema")
        async def get_schema():
            schema_path = (
                Path(__file__).resolve().parent.parent.parent / "_conf_schema.json"
            )
            if schema_path.exists():
                try:
                    text = await asyncio.to_thread(
                        schema_path.read_text, encoding="utf-8"
                    )
                    return json.loads(text)
                except Exception as exc:
                    logger.error(f"[Plana] 读取 schema 失败: {exc}")
            return {}

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            if self._auth_enabled:
                token = websocket.query_params.get("token", "")
                if not self._verify_token(token):
                    await websocket.close(code=1008)
                    return
            await websocket.accept()
            self._ws_connections.append(websocket)
            try:
                await websocket.send_json(
                    {"type": "connected", "message": "Plana Core WebSocket 已连接"}
                )
                while True:
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                    except Exception:
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                logger.debug(f"[Plana] WebSocket 异常: {exc}")
            finally:
                if websocket in self._ws_connections:
                    self._ws_connections.remove(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """向所有已连接的 WebSocket 客户端广播消息。"""
        to_rm: list[Any] = []
        for ws in list(self._ws_connections):
            try:
                await ws.send_json(payload)
            except Exception:
                to_rm.append(ws)
        for ws in to_rm:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动独立 Web 服务器。"""
        if not _FASTAPI_OK:
            logger.error("[Plana] FastAPI 未安装，无法启动独立 Web 管理端。")
            return
        wa = self._web_admin()
        if not wa.get("enabled", False):
            return
        host = str(wa.get("host", "0.0.0.0"))
        port = int(wa.get("port", 6180))
        cfg = uvicorn.Config(
            self.app, host=host, port=port, log_level="warning", access_log=False
        )
        self._server = uvicorn.Server(cfg)

        async def _serve():
            try:
                await self._server.serve()
            except Exception as exc:
                logger.error(f"[Plana] 独立 Web 管理端异常: {exc}")

        self._server_task = asyncio.create_task(_serve())

        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(3600)
                    now = time.time()
                    expired = [k for k, v in self._tokens.items() if now > v]
                    for k in expired:
                        self._tokens.pop(k, None)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        await asyncio.sleep(0.1)
        logger.info(f"[Plana] 独立 Web 管理端已启动: http://{host}:{port}")

    async def stop(self) -> None:
        """停止独立 Web 服务器。"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._server:
            self._server.should_exit = True
        if self._server_task:
            try:
                await asyncio.wait_for(self._server_task, timeout=5)
            except Exception:
                pass
        self._ws_connections.clear()
        logger.info("[Plana] 独立 Web 管理端已停止。")
