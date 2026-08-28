from __future__ import annotations

import asyncio
import json
import secrets

from quart import jsonify, request

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Record
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr

from .core.bridge import NachoSidecarBridge
from .core.config import normalize_plana_config
from .core.memory import (
    ALL_MEMORY_KINDS,
    MEMORY_KIND_ARONA_HANDOFF,
    MEMORY_KIND_TASK_FACT,
)
from .core.runtime import PlanaRuntime
from .core.utils.time_utils import is_quiet_time
from .core.web import PlanaWebAPI, PlanaWebServer


class PlanaCorePlugin(Star):
    """Plana persona, memory, state and tool runtime plugin."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.config = normalize_plana_config(config)
        data_dir = StarTools.get_data_dir("astrbot_plugin_plana_core")
        self.runtime = PlanaRuntime(data_dir, self.config)
        self.arona_api_token = str(self.config.get("arona_api_token", ""))
        self.debug_api_token = str(self.config.get("debug_api_token", ""))
        self.enable_arona_api = bool(self.config.get("enable_arona_api", False))
        self.enable_debug_api = bool(self.config.get("enable_debug_api", False))
        self.enable_web_dashboard = bool(self.config.get("enable_web_dashboard", True))
        self.enable_auto_maintenance = bool(
            self.config.get("enable_auto_maintenance", False)
        )
        self.auto_maintenance_interval = int(
            self.config.get("auto_maintenance_interval_hours", 6)
        )
        self.quiet_hours: str = str(self.config.get("quiet_hours", "") or "")
        self._quiet_hours_active: bool = False  # 跟踪当前是否处于 quiet 状态
        self._maintenance_task: asyncio.Task | None = None
        self._web_api: PlanaWebAPI | None = None
        # 独立 Web 管理服务器（FastAPI + Uvicorn，独立端口）
        self._web_server: PlanaWebServer | None = None
        # 内置 NachoBot Sidecar 通讯桥
        self._nacho_bridge = NachoSidecarBridge(self.config)

    async def initialize(self) -> None:
        self.runtime.initialize()
        # -- Arona bridge APIs --
        if self.enable_arona_api:
            self.context.register_web_api(
                "/plana_core/arona/state",
                self._api_arona_state,
                ["GET"],
                "Reserved Arona bridge state endpoint",
            )
            self.context.register_web_api(
                "/plana_core/arona/bridge",
                self._api_arona_bridge,
                ["POST"],
                "Reserved Arona bridge standard payload endpoint",
            )
            self.context.register_web_api(
                "/plana_core/arona/task",
                self._api_arona_task,
                ["POST"],
                "Reserved Arona bridge task endpoint",
            )

        # -- Debug API --
        if self.enable_debug_api:
            self.context.register_web_api(
                "/plana_core/debug/status",
                self._api_debug_status,
                ["GET"],
                "Plana Core readonly debug status endpoint",
            )
        # -- Web Dashboard & Management APIs --
        if self.enable_web_dashboard:
            self._web_api = PlanaWebAPI(
                self.runtime,
                self.debug_api_token,
                provider_getter=self.context.get_using_provider,
            )
            self._register_dashboard_apis()
        # -- 独立 Web 管理服务器 --
        web_admin = self.config.get("web_admin", {}) or {}
        if web_admin.get("enabled", False):
            self._web_server = PlanaWebServer(
                self.runtime,
                self.config,
                provider_getter=self.context.get_using_provider,
            )
            await self._web_server.start()
        # -- Background maintenance loop --
        if self.enable_auto_maintenance:
            self._maintenance_task = asyncio.get_event_loop().create_task(
                self._maintenance_loop()
            )
            logger.info(
                "Plana auto-maintenance enabled: interval=%dh",
                self.auto_maintenance_interval,
            )
        logger.info(
            "Plana core initialized: arona_api=%s debug_api=%s web_dashboard=%s web_admin=%s",
            self.enable_arona_api,
            self.enable_debug_api,
            self.enable_web_dashboard,
            web_admin.get("enabled", False),
        )
        if self.runtime.enable_recall_tool:
            self._register_recall_tool()
        # -- Built-in NachoBot Sidecar bridge --
        if self._nacho_bridge.enabled:
            await self._nacho_bridge.start()
            if self._nacho_bridge.enable_active_send_api:
                self.context.register_web_api(
                    "/plana_core/nacho/send",
                    self._api_nacho_send_message,
                    ["POST"],
                    "Built-in NachoBot active send bridge",
                )
            logger.info(
                "Plana built-in nacho bridge enabled: %s%s",
                self._nacho_bridge.sidecar_url,
                self._nacho_bridge.message_endpoint,
            )

    def _register_dashboard_apis(self) -> None:
        """Register all web dashboard routes."""
        api = self._web_api
        if api is None:
            return
        routes = [
            ("/plana/dashboard", api.serve_dashboard, ["GET"], "Dashboard HTML page"),
            ("/plana/api/overview", api.api_overview, ["GET"], "Overview JSON"),
            ("/plana/api/memories", api.api_memories, ["GET"], "Memories JSON"),
            (
                "/plana/api/retrieve-test",
                api.api_retrieve_test,
                ["GET"],
                "Retrieve lab JSON",
            ),
            ("/plana/api/profile", api.api_profile, ["GET"], "Profile JSON"),
            (
                "/plana/api/bridge-status",
                api.api_bridge_status,
                ["GET"],
                "Bridge status JSON",
            ),
            (
                "/plana/api/context-preview",
                api.api_context_preview,
                ["GET"],
                "Context preview JSON",
            ),
            ("/plana/api/concepts", api.api_concepts, ["GET"], "Concepts JSON"),
            ("/plana/api/relations", api.api_relations, ["GET"], "Relations JSON"),
            ("/plana/api/tasks", api.api_tasks, ["GET"], "Tasks JSON"),
            (
                "/plana/api/maintenance-status",
                api.api_maintenance_status,
                ["GET"],
                "Maintenance status JSON",
            ),
            (
                "/plana/api/backup",
                api.api_maintenance_backup,
                ["POST"],
                "Create maintenance backup",
            ),
            (
                "/plana/api/rebuild-indexes",
                api.api_maintenance_rebuild_indexes,
                ["POST"],
                "Rebuild memory indexes",
            ),
            ("/plana/api/maintain", api.api_maintain, ["POST"], "Trigger maintenance"),
            (
                "/plana/api/delete-memory",
                api.api_delete_memory,
                ["POST"],
                "Delete episodic memory",
            ),
            (
                "/plana/api/delete-semantic",
                api.api_delete_semantic,
                ["POST"],
                "Delete semantic memory",
            ),
            (
                "/plana/api/clean-orphans",
                api.api_clean_orphans,
                ["POST"],
                "Clean orphan links and decay events",
            ),
            ("/plana/api/audit", api.api_audit, ["GET"], "Audit events JSON"),
            (
                "/plana/api/proactive",
                api.api_proactive_list,
                ["GET"],
                "Proactive tasks list",
            ),
            (
                "/plana/api/proactive/enqueue",
                api.api_proactive_enqueue,
                ["POST"],
                "Enqueue proactive task",
            ),
            (
                "/plana/api/proactive/poll",
                api.api_proactive_poll,
                ["POST"],
                "Poll ready proactive tasks",
            ),
            (
                "/plana/api/proactive/deliver",
                api.api_proactive_deliver,
                ["POST"],
                "Mark proactive task delivered",
            ),
            (
                "/plana/api/proactive/cancel",
                api.api_proactive_cancel,
                ["POST"],
                "Cancel proactive task",
            ),
            (
                "/plana/api/feedback",
                api.api_feedback_list,
                ["GET"],
                "Feedback queue list",
            ),
            (
                "/plana/api/feedback/useful",
                api.api_feedback_useful,
                ["POST"],
                "Submit useful memory feedback",
            ),
            (
                "/plana/api/feedback/not-useful",
                api.api_feedback_not_useful,
                ["POST"],
                "Submit not-useful memory feedback",
            ),
            (
                "/plana/api/feedback/new-memory",
                api.api_feedback_new_memory,
                ["POST"],
                "Suggest new memory",
            ),
            (
                "/plana/api/feedback/merge",
                api.api_feedback_merge,
                ["POST"],
                "Suggest memory merge",
            ),
            (
                "/plana/api/scope/aliases",
                api.api_scope_aliases,
                ["GET"],
                "List scope aliases",
            ),
            (
                "/plana/api/scope/alias",
                api.api_scope_add_alias,
                ["POST"],
                "Add scope alias",
            ),
            (
                "/plana/api/scope/remove-alias",
                api.api_scope_remove_alias,
                ["POST"],
                "Remove scope alias",
            ),
            (
                "/plana/api/scope/migrate",
                api.api_scope_migrate,
                ["POST"],
                "Migrate memories between scopes",
            ),
        ]
        for route, handler, methods, desc in routes:
            self.context.register_web_api(route, handler, methods, desc)

    def _register_recall_tool(self) -> None:
        """Register Plana active recall as an LLM function tool."""
        StarTools.register_llm_tool(
            "plana_recall_memory",
            [
                {
                    "type": "string",
                    "name": "query",
                    "description": "Short keywords for long-term memory recall; do not paste the full user message.",
                },
                {
                    "type": "number",
                    "name": "k",
                    "description": "Maximum result count. Default is configured by Plana Core.",
                },
                {
                    "type": "string",
                    "name": "kind",
                    "description": "Optional typed memory kind filter, such as user_preference, task_fact or risk_event.",
                },
            ],
            "Recall Plana Core long-term memory with RRF fused episodic, semantic and concept routes.",
            self._llm_tool_recall_memory,
        )

    async def _llm_tool_recall_memory(
        self,
        query: str = "",
        k: int | float | str | None = None,
        kind: str = "",
        **kwargs,
    ) -> str:
        event = kwargs.get("event")
        scope = getattr(event, "unified_msg_origin", "global") or "global"
        result = self.runtime.recall_memory(scope, str(query), str(kind or ""), k)
        return json.dumps(result, ensure_ascii=False)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=20)
    async def on_any_message(self, event: AstrMessageEvent):
        self.runtime.ingest_event(event)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def on_nacho_bridge_message(self, event: AstrMessageEvent):
        """Forward messages to NachoBot Sidecar when built-in bridge is enabled."""
        if not self._nacho_bridge.should_forward_event(event):
            return
        response = await self._nacho_bridge.forward_event(event)
        if not response:
            return
        plana_results = await self._nacho_bridge.relay_plana_requests(
            event, response, self._handle_arona_bridge_payload
        )
        if plana_results:
            response["plana_results"] = plana_results
            payload = await self._nacho_bridge._build_payload(event)
            await self._nacho_bridge.post_plana_results(payload, plana_results)
        if self._nacho_bridge.send_replies and response.get("should_reply", False):
            for reply in response.get("replies", []):
                await self._nacho_bridge.send_reply(event, reply)
        if self._nacho_bridge.should_stop_pipeline(response):
            event.call_llm = True
            event.stop_event()
            yield

    @filter.on_llm_request(priority=20)
    async def on_llm_request(self, event: AstrMessageEvent, request_obj) -> None:
        query = event.get_message_str().strip()
        provider = self.context.get_using_provider()
        query_plan = await self.runtime.plan_memory_query(query, provider)
        memory_query = query_plan.query if query_plan.should_retrieve else query
        prompt_block = self.runtime.build_prompt_for_event(event, memory_query)
        if not prompt_block:
            return

        selected = await self.runtime.select_concept_nodes_for_prompt(
            memory_query, provider
        )
        if selected:
            # Rebuild prompt with LLM-filtered concept nodes.
            state = self.runtime.storage.get_state("global", self.runtime.mode)
            identity = self.runtime.identity_from_event(event)
            active_context = self.runtime.memory_activator.activate(
                memory_query, event.unified_msg_origin, identity, []
            )
            prompt_block = self.runtime.prompt_builder.build(
                state,
                identity,
                active_context,
                self.runtime.max_prompt_chars,
                concept_nodes=selected,
            )
        base_prompt = getattr(request_obj, "system_prompt", "") or ""
        request_obj.system_prompt = f"{base_prompt}\n{prompt_block}".strip()

    @filter.on_llm_response(priority=20)
    async def on_llm_response(self, event: AstrMessageEvent, response) -> None:
        text = str(getattr(response, "completion_text", "") or "")
        self.runtime.record_response(event, text)
        if text.strip():
            provider = self.context.get_using_provider()
            await self.runtime.extract_and_index_concepts(text, provider)
            await self.runtime.extract_structured_memories(event, text, provider)
            # Probabilistic LLM-driven mood update aligned with NachoBot ChatMood.
            await self.runtime.update_mood_by_response(text, provider)

    @filter.command("plana")
    async def plana(
        self, event: AstrMessageEvent, action: str = "status", value: GreedyStr = ""
    ):
        """Simplified Plana command — see /plana help for details."""
        action = action.strip().lower()
        value = str(value).strip()
        if action == "status":
            yield event.plain_result(self.runtime.status_text())
            return
        if action == "mode":
            if not self.runtime.set_mode(value):
                yield event.plain_result(
                    "mode must be one of: standby/observing/tasking/checking/"
                    "risk_review/waiting_confirm/reporting/handoff_to_arona/silent"
                )
                return
            yield event.plain_result(f"Plana mode updated: {value}")
            return
        if action == "search":
            yield event.plain_result(self.runtime.search_text(event, value))
            return
        if action == "remember":
            yield event.plain_result(self.runtime.remember_text(event, value))
            return
        if action == "task":
            yield event.plain_result(self.runtime.task_text(event, value))
            return
        if action == "tts":
            if not value:
                yield event.plain_result("用法：/plana tts <要朗读的文字>")
                return
            tts = self.context.get_using_tts_provider(event.unified_msg_origin)
            if tts is None:
                yield event.plain_result("当前未配置 TTS Provider，无法生成语音。")
                return
            try:
                audio_path = await tts.get_audio(value)
                yield event.result([Record.fromFileSystem(audio_path)])
            except Exception as e:  # noqa: BLE001
                yield event.plain_result(f"TTS 生成失败：{e}")
            return
        # -- help / fallback --
        yield event.plain_result(
            "Plana Core commands:\n"
            "  /plana            — 状态概览\n"
            "  /plana mode <m>   — 切换模式\n"
            "  /plana search <q> — 搜索记忆\n"
            "  /plana remember <text> — 记住事实\n"
            "  /plana task list|add|done|cancel\n"
            "  /plana tts <text> — TTS 语音朗读\n"
            "  /plana help       — 显示此帮助\n"
            "管理面板: /api/plug/plana/dashboard"
        )

    async def _api_arona_state(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "status": self.runtime.arona_contract.status()})

    async def _api_arona_task(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not self.runtime.arona_contract.enabled:
            return jsonify(self.runtime.arona_contract.disabled_result()), 403
        task = self.runtime.arona_contract.normalize_task(payload)
        return jsonify(
            {
                "ok": False,
                "error": "arona_bridge_plugin_required",
                "task": self.runtime.arona_contract.describe_task(task),
            }
        ), 501

    async def _api_arona_bridge(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if not self.runtime.arona_contract.enabled:
            return jsonify(self.runtime.arona_contract.disabled_result()), 403
        normalized = self.runtime.arona_contract.normalize_payload(payload)
        result = self._handle_arona_bridge_payload(normalized)
        return jsonify(self.runtime.arona_contract.result_report(normalized, result))

    def _handle_arona_bridge_payload(self, payload: dict) -> dict[str, object]:
        kind = str(payload.get("kind", "unknown"))
        scope_id = str(payload.get("scope_id", "global")) or "global"
        user_id = str(payload.get("user_id", "arona")) or "arona"
        content = str(payload.get("content", "")).strip()
        payload_data = (
            payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        )
        if kind == "memory_query":
            limit = self._bridge_limit(payload_data.get("limit", 8), 20)
            target_kinds = self._bridge_target_kinds(payload_data)
            memories = self._search_bridge_memories(
                scope_id,
                content,
                target_kinds,
                limit,
            )
            recall = self.runtime.recall_memory(
                scope_id,
                content,
                str(payload_data.get("kind") or ""),
                limit,
            )
            return {
                "kind": kind,
                "target_kinds": target_kinds,
                "items": [self._bridge_memory_item(item) for item in memories],
                "fused_results": recall.get("results", []),
                "routes": recall.get("routes", {}),
            }
        if kind == "task_delegate":
            task = self.runtime.arona_contract.normalize_task(payload)
            objective = task.objective or content
            if not objective:
                return {
                    "kind": kind,
                    "created": False,
                    "error": "empty_objective",
                    "task": self.runtime.arona_contract.describe_task(task),
                }
            if not self.runtime.enable_task_queue:
                return {
                    "kind": kind,
                    "created": False,
                    "error": "task_queue_disabled",
                    "task": self.runtime.arona_contract.describe_task(task),
                }
            record = self.runtime.task_queue.add(scope_id, user_id, objective)
            if record:
                self.runtime.storage.add_memory(
                    user_id,
                    scope_id,
                    MEMORY_KIND_TASK_FACT,
                    f"Arona delegated task #{record.id}: {record.objective}",
                    0.72,
                    "arona_bridge",
                )
            return {
                "kind": kind,
                "created": bool(record),
                "task": self.runtime.arona_contract.describe_task(task),
                "record": self._bridge_task_item(record),
            }
        if kind == "result_report":
            result_summary = str(
                payload_data.get("result_summary")
                or payload_data.get("summary")
                or payload_data.get("result")
                or content
            ).strip()
            objective = str(
                payload_data.get("objective") or content or "bridge result"
            ).strip()
            tool_name = str(payload_data.get("tool_name") or "nachobot_bridge").strip()
            success = self._bridge_success(payload_data.get("success", True))
            task_id = self._bridge_int(payload_data.get("task_id", 0), 0)
            if not result_summary:
                return {"kind": kind, "stored": False, "error": "empty_result"}
            counts = self.runtime.record_tool_result(
                scope_id,
                user_id,
                tool_name,
                objective,
                result_summary,
                success,
                str(payload_data.get("risk_level") or "normal"),
                task_id,
            )
            return {"kind": kind, "stored": True, "counts": counts}
        if kind in {"context_sync", "emotional_handoff"}:
            if content:
                self.runtime.storage.add_memory(
                    user_id,
                    scope_id,
                    MEMORY_KIND_ARONA_HANDOFF,
                    content,
                    0.6,
                    "arona_bridge",
                )
            return {"kind": kind, "stored": bool(content)}
        return {"kind": kind, "error": "unsupported_kind"}

    def _bridge_limit(self, value: object, maximum: int) -> int:
        limit = self._bridge_int(value, 8)
        return max(1, min(limit, maximum))

    def _bridge_int(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _bridge_success(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text not in {"0", "false", "failed", "error", "no"}

    def _bridge_target_kinds(self, payload_data: dict) -> list[str]:
        raw = payload_data.get("target_kinds") or payload_data.get("kinds") or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        if payload_data.get("kind"):
            raw.append(str(payload_data.get("kind")))
        result = []
        for item in raw:
            kind = str(item).strip()
            if kind in ALL_MEMORY_KINDS and kind not in result:
                result.append(kind)
        return result[:6]

    def _search_bridge_memories(
        self,
        scope_id: str,
        query: str,
        target_kinds: list[str],
        limit: int,
    ):
        if not target_kinds:
            if query:
                return self.runtime.storage.search_memories(scope_id, query, limit)
            return self.runtime.storage.recent_memories(scope_id, limit)
        items = []
        seen = set()
        for memory_kind in target_kinds:
            candidates = (
                self.runtime.storage.search_memories_by_kind(
                    scope_id, query, memory_kind, limit
                )
                if query
                else self.runtime.storage.recent_memories_by_kind(
                    scope_id, memory_kind, limit
                )
            )
            for item in candidates:
                if item.id not in seen:
                    seen.add(item.id)
                    items.append(item)
        items.sort(key=lambda item: (item.importance, item.created_at), reverse=True)
        return items[:limit]

    def _bridge_memory_item(self, item) -> dict[str, object]:
        return {
            "id": item.id,
            "kind": item.kind,
            "content": item.content,
            "importance": round(item.importance, 3),
            "source": item.source,
            "created_at": item.created_at,
        }

    def _bridge_task_item(self, item) -> dict[str, object] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "scope_id": item.scope_id,
            "owner_id": item.owner_id,
            "objective": item.objective,
            "status": item.status,
            "risk_level": item.risk_level,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    async def _api_debug_status(self):
        if not self._debug_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return jsonify({"ok": True, "status": self.runtime.debug_status_payload()})

    def _authorized(self) -> bool:
        return self._token_authorized(self.arona_api_token)

    def _debug_authorized(self) -> bool:
        if not self.debug_api_token:
            return False
        return self._token_authorized(self.debug_api_token)

    def _token_authorized(self, expected_token: str) -> bool:
        if not expected_token:
            return True
        token = request.headers.get("X-Plana-Token", "").strip()
        if not token:
            token = (
                request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            )
        # 使用 secrets.compare_digest 防止时序侧信道攻击
        return secrets.compare_digest(token, expected_token)

    # -- Built-in NachoBot Sidecar active send API --

    async def _api_nacho_send_message(self):
        """Allow NachoBot Sidecar to actively send messages through AstrBot."""
        token = request.headers.get("X-Nacho-Token", "").strip()
        if not token:
            token = (
                request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            )
        if not self._nacho_bridge.active_token_authorized(token):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid payload"}), 400
        session = str(payload.get("session", ""))
        replies = payload.get("replies", [])
        if not session or not isinstance(replies, list):
            return jsonify({"ok": False, "error": "invalid payload"}), 400
        sent = 0
        for reply in replies:
            if isinstance(reply, dict):
                chain = self._nacho_bridge._reply_to_chain(reply)
                if chain and await self.context.send_message(session, chain):
                    sent += 1
        return jsonify({"ok": True, "sent": sent})

    async def terminate(self) -> None:
        """插件卸载或重载时优雅停止所有后台任务。"""
        if self._maintenance_task and not self._maintenance_task.done():
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
        if self._web_server:
            try:
                await self._web_server.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Plana web server stop error", exc_info=True)
            self._web_server = None
        if self.runtime.enable_recall_tool:
            try:
                StarTools.unregister_llm_tool("plana_recall_memory")
            except Exception:  # noqa: BLE001
                logger.debug("Plana recall tool unregister skipped", exc_info=True)
        # -- Stop built-in nacho bridge --
        if self._nacho_bridge.enabled:
            try:
                await self._nacho_bridge.stop()
            except Exception:  # noqa: BLE001
                logger.debug("Nacho bridge stop error", exc_info=True)
        logger.info("Plana core terminated.")

    async def _maintenance_loop(self) -> None:
        """Unified background maintenance: quiet_hours check + consolidate + decay + accumulate."""
        interval = max(1, self.auto_maintenance_interval) * 3600
        while True:
            try:
                await asyncio.sleep(interval)
                # -- quiet_hours 自动 silent 切换 --
                if self.quiet_hours:
                    in_quiet = is_quiet_time(self.quiet_hours)
                    if in_quiet and not self._quiet_hours_active:
                        self._quiet_hours_active = True
                        if self.runtime.mode != "silent":
                            self.runtime.set_mode("silent")
                            logger.info(
                                "Plana quiet_hours started (%s): switched to silent",
                                self.quiet_hours,
                            )
                    elif not in_quiet and self._quiet_hours_active:
                        self._quiet_hours_active = False
                        if self.runtime.mode == "silent":
                            self.runtime.set_mode("standby")
                            logger.info(
                                "Plana quiet_hours ended (%s): restored to standby",
                                self.quiet_hours,
                            )
                # -- Consolidate --
                if self.runtime.enable_memory_consolidation:
                    self.runtime.memory_consolidator.consolidate_scope("global", None)
                # -- Decay --
                if self.runtime.enable_memory_decay:
                    self.runtime.memory_decay.decay_scope("global")
                # -- Accumulate concepts --
                provider = self.context.get_using_provider()
                if provider is not None:
                    result = await self.runtime.auto_accumulate_concepts(
                        "global", provider
                    )
                    if result.get("written", 0) > 0:
                        logger.info(
                            "Plana maintenance: accumulate written=%d",
                            result.get("written", 0),
                        )
                # -- pressure/focus 自动衰减（对齐 NachoBot MoodRegressionTask，无 LLM）--
                self.runtime.decay_state()
                # -- Proactive queue auto-poll + bridge delivery --
                ready_tasks = self.runtime.proactive_queue.poll_ready(limit=5)
                if ready_tasks:
                    delivered = await self._nacho_bridge.deliver_proactive(ready_tasks)
                    for task in ready_tasks[:delivered]:
                        self.runtime.proactive_queue.mark_delivered(task["id"])
                    if delivered:
                        logger.info(
                            "Plana maintenance: proactive delivered=%d/%d",
                            delivered,
                            len(ready_tasks),
                        )
                # -- Proactive queue cleanup (old delivered/expired/cancelled) --
                cleaned = self.runtime.proactive_queue.cleanup_old(max_age_days=30)
                if cleaned:
                    logger.debug("Plana maintenance: proactive cleanup=%d", cleaned)
                logger.debug("Plana maintenance cycle completed")
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                logger.debug("Plana maintenance cycle error", exc_info=True)
