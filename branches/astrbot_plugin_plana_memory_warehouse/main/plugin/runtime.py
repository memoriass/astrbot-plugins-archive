from __future__ import annotations

import time
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.star.filter.command import GreedyStr
from quart import jsonify, request

from .capture import build_event_payload
from .config import bounded_int, normalize_config, prefixes
from .filters import PlanaWarehousePassiveCaptureFilter, set_active_warehouse
from .http_api import contract_error, json_payload, request_values
from .maintenance_api import MemoryWarehouseMaintenanceApiMixin
from .store import CONTRACT_VERSION, DEFAULT_BULK_LIMIT, MemoryWarehouseStore


class PlanaMemoryWarehousePlugin(MemoryWarehouseMaintenanceApiMixin, Star):
    """Optional raw episodic memory warehouse for the Plana plugin family."""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = normalize_config(config)
        self.enabled = bool(self.config.get("enabled", True))
        self.enable_core_api = bool(self.config.get("enable_core_api", True))
        self.allow_commands = bool(self.config.get("allow_commands", False))
        self.capture_messages = bool(self.config.get("capture_messages", False))
        self.capture_llm_responses = bool(self.config.get("capture_llm_responses", False))
        self.capture_commands = bool(self.config.get("capture_commands", False))
        self.min_content_chars = bounded_int(
            self.config.get("min_content_chars", 1),
            1,
            minimum=1,
            maximum=200,
        )
        self.max_search_limit = bounded_int(
            self.config.get("max_search_limit", 50),
            50,
            minimum=1,
            maximum=500,
        )
        self.max_bulk_items = bounded_int(
            self.config.get("max_bulk_items", DEFAULT_BULK_LIMIT),
            DEFAULT_BULK_LIMIT,
            minimum=1,
            maximum=5000,
        )
        self.retention_days = bounded_int(
            self.config.get("retention_days", 0),
            0,
            minimum=0,
            maximum=3650,
        )
        self.maintenance_on_start = bool(self.config.get("maintenance_on_start", False))
        self.excluded_prefixes = prefixes(self.config.get("excluded_prefixes", ""))
        self.store = MemoryWarehouseStore(
            StarTools.get_data_dir("astrbot_plugin_plana_memory_warehouse"),
            max_content_chars=bounded_int(
                self.config.get("max_content_chars", 4000),
                4000,
                minimum=200,
                maximum=100_000,
            ),
        )

    async def initialize(self) -> None:
        if not self.enabled:
            logger.info("Plana Memory Warehouse disabled")
            return
        set_active_warehouse(self)
        self.store.initialize()
        if self.maintenance_on_start:
            self._run_startup_maintenance()
        if self.enable_core_api:
            self._register_web_apis()
        logger.info(
            "Plana Memory Warehouse initialized: capture_messages=%s capture_llm_responses=%s",
            self.capture_messages,
            self.capture_llm_responses,
        )

    async def terminate(self) -> None:
        set_active_warehouse(None)
        logger.info("Plana Memory Warehouse terminated")

    async def on_any_message(self, event: AstrMessageEvent) -> None:
        return

    def _capture_message(self, event: AstrMessageEvent) -> None:
        if not self.enabled or not self.capture_messages:
            return
        payload = build_event_payload(
            event,
            role="user",
            event_type="message",
            min_content_chars=self.min_content_chars,
            capture_commands=self.capture_commands,
            excluded_prefixes=self.excluded_prefixes,
        )
        if payload is None:
            return
        result = self.store.ingest(payload)
        if not result.get("ok"):
            logger.debug(
                "Plana Memory Warehouse skipped message capture: %s",
                result.get("error"),
            )

    async def capture_llm_response(self, event: AstrMessageEvent, response: Any | None = None) -> None:
        if not self.enabled or not self.capture_llm_responses:
            return
        if response is None:
            return
        payload = build_event_payload(
            event,
            role="assistant",
            event_type="llm_response",
            min_content_chars=self.min_content_chars,
            capture_commands=self.capture_commands,
            excluded_prefixes=self.excluded_prefixes,
            content_override=str(getattr(response, "completion_text", "") or ""),
        )
        if payload is None:
            return
        result = self.store.ingest(payload)
        if not result.get("ok"):
            logger.debug(
                "Plana Memory Warehouse skipped response capture: %s",
                result.get("error"),
            )

    async def plana_warehouse_status(self, event: AstrMessageEvent):
        """Show Memory Warehouse status."""
        if not self.allow_commands:
            return
        status = self.store.status() if self.enabled else {"ok": False}
        yield event.plain_result(
            "Plana Memory Warehouse\n"
            f"enabled={self.enabled}\n"
            f"core_api={self.enable_core_api}\n"
            f"capture_messages={self.capture_messages}\n"
            f"capture_llm_responses={self.capture_llm_responses}\n"
            f"events={status.get('event_count', 0)}\n"
            f"scopes={status.get('scope_count', 0)}\n"
            f"fts={status.get('fts_count', 0)}\n"
            f"index_consistent={status.get('index_consistent', False)}\n"
            f"contract={CONTRACT_VERSION}"
        )

    async def plana_warehouse_search(self, event: AstrMessageEvent, query: GreedyStr = ""):
        """Search warehouse evidence from chat for debugging."""
        if not self.allow_commands:
            return
        text = " ".join(str(query or "").split())
        if not text:
            yield event.plain_result("用法：/plana_warehouse_search <关键词>")
            return
        origin = self._event_origin(event)
        if not origin:
            yield event.plain_result("Memory Warehouse origin unavailable; search skipped.")
            return
        result = self.store.search(
            query=text,
            unified_msg_origin=origin,
            limit=5,
        )
        lines = [f"Memory Warehouse 命中 {result['count']} 条："]
        for item in result["results"][:5]:
            lines.append(f"- {item['evidence_id']}: {item['snippet']}")
        yield event.plain_result("\n".join(lines))

    async def plana_warehouse_recent(self, event: AstrMessageEvent, limit: int = 5):
        """Show recent warehouse evidence."""
        if not self.allow_commands:
            return
        origin = self._event_origin(event)
        if not origin:
            yield event.plain_result("Memory Warehouse origin unavailable; recent skipped.")
            return
        result = self.store.recent(
            unified_msg_origin=origin,
            limit=bounded_int(limit, 5, minimum=1, maximum=20),
        )
        lines = [f"Memory Warehouse 最近 {result['count']} 条："]
        for item in result["results"]:
            lines.append(
                f"- {item['evidence_id']} [{item['role']}/{item['event_type']}]: "
                f"{item['snippet']}"
            )
        yield event.plain_result("\n".join(lines))

    async def plana_warehouse_rebuild_index(
        self,
        event: AstrMessageEvent,
        confirm: str = "",
    ):
        """Rebuild the warehouse FTS index."""
        if not self.allow_commands:
            return
        if str(confirm or "").strip().lower() not in {"confirm", "yes", "确认"}:
            yield event.plain_result(
                "Memory Warehouse index rebuild requires confirm."
            )
            return
        result = self.store.rebuild_index()
        yield event.plain_result(
            f"Memory Warehouse index rebuilt: indexed={result.get('indexed', 0)}"
        )

    async def plana_warehouse_prune(
        self,
        event: AstrMessageEvent,
        days: int = 0,
        confirm: str = "",
    ):
        """Preview or execute retention pruning."""
        if not self.allow_commands:
            return
        safe_days = bounded_int(days, 0, minimum=0, maximum=3650)
        if safe_days <= 0:
            yield event.plain_result("用法：/plana_warehouse_prune <days> [confirm]")
            return
        dry_run = str(confirm or "").strip().lower() not in {"confirm", "yes", "确认"}
        result = self.store.prune(
            before_ts=int(time.time()) - safe_days * 86_400,
            limit=50_000,
            dry_run=dry_run,
        )
        if dry_run:
            yield event.plain_result(
                "Memory Warehouse prune preview: "
                f"matched={result.get('matched', 0)}. "
                "追加 confirm 才会删除。"
            )
            return
        yield event.plain_result(
            f"Memory Warehouse pruned: deleted={result.get('deleted', 0)}"
        )

    def _register_web_apis(self) -> None:
        routes = (
            (
                "/plana_warehouse/state",
                self._api_state,
                ["GET"],
                "Plana Memory Warehouse state endpoint",
            ),
            (
                "/plana_warehouse/evidence/ingest",
                self._api_ingest,
                ["POST"],
                "Plana Memory Warehouse evidence ingest endpoint",
            ),
            (
                "/plana_warehouse/evidence/bulk-ingest",
                self._api_bulk_ingest,
                ["POST"],
                "Plana Memory Warehouse evidence bulk ingest endpoint",
            ),
            (
                "/plana_warehouse/evidence/search",
                self._api_search,
                ["GET", "POST"],
                "Plana Memory Warehouse evidence search endpoint",
            ),
            (
                "/plana_warehouse/evidence/recent",
                self._api_recent,
                ["GET", "POST"],
                "Plana Memory Warehouse recent evidence endpoint",
            ),
            (
                "/plana_warehouse/evidence/get",
                self._api_get,
                ["GET"],
                "Plana Memory Warehouse evidence detail endpoint",
            ),
            (
                "/plana_warehouse/maintenance/rebuild-index",
                self._api_rebuild_index,
                ["POST"],
                "Plana Memory Warehouse index rebuild endpoint",
            ),
            (
                "/plana_warehouse/maintenance/prune",
                self._api_prune,
                ["POST"],
                "Plana Memory Warehouse retention prune endpoint",
            ),
            (
                "/plana_warehouse/maintenance/backup",
                self._api_backup,
                ["POST"],
                "Plana Memory Warehouse online backup endpoint",
            ),
            (
                "/plana_warehouse/maintenance/backup/validate",
                self._api_validate_backup,
                ["POST"],
                "Plana Memory Warehouse backup validation endpoint",
            ),
            (
                "/plana_warehouse/maintenance/restore-candidate",
                self._api_restore_candidate,
                ["POST"],
                "Plana Memory Warehouse restore candidate endpoint",
            ),
            (
                "/plana_warehouse/maintenance/delete-evidence",
                self._api_delete_evidence,
                ["POST"],
                "Plana Memory Warehouse confirmed evidence deletion endpoint",
            ),
        )
        for route, handler, methods, desc in routes:
            self.context.register_web_api(route, handler, methods, desc)

    async def _api_state(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = self.store.status()
        payload.update(
            {
                "enabled": self.enabled,
                "source": "astrbot_plugin_plana_memory_warehouse",
                "core_api": self.enable_core_api,
                "policy_owner": "plana_core",
                "stores_raw_archive": True,
                "capture_messages": self.capture_messages,
                "capture_llm_responses": self.capture_llm_responses,
                "capture_commands": self.capture_commands,
                "retention_days": self.retention_days,
                "max_search_limit": self.max_search_limit,
            }
        )
        return jsonify(payload)

    async def _api_ingest(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        result = self.store.ingest(payload)
        return jsonify(result), 200 if result.get("ok") else 400

    async def _api_bulk_ingest(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await json_payload()
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            return jsonify(contract_error()), 400
        items = payload.get("items")
        if not isinstance(items, list):
            return jsonify({"ok": False, "error": "items_must_be_array"}), 400
        result = self.store.bulk_ingest(items, max_items=self.max_bulk_items)
        return jsonify(result), 200 if result.get("ok") else 207

    async def _api_search(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request_values()
        limit = bounded_int(
            payload.get("limit"),
            10,
            minimum=1,
            maximum=self.max_search_limit,
        )
        result = self.store.search(
            query=str(payload.get("query") or ""),
            scope_id=str(payload.get("scope_id") or ""),
            scope_ids=payload.get("scope_ids"),
            shared_scope_ids=payload.get("shared_scope_ids"),
            unified_msg_origin=str(payload.get("unified_msg_origin") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            limit=limit,
        )
        return jsonify(result)

    async def _api_recent(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = await request_values()
        limit = bounded_int(
            payload.get("limit"),
            20,
            minimum=1,
            maximum=self.max_search_limit,
        )
        result = self.store.recent(
            scope_id=str(payload.get("scope_id") or ""),
            scope_ids=payload.get("scope_ids"),
            shared_scope_ids=payload.get("shared_scope_ids"),
            unified_msg_origin=str(payload.get("unified_msg_origin") or ""),
            actor_id=str(payload.get("actor_id") or ""),
            role=str(payload.get("role") or ""),
            event_type=str(payload.get("event_type") or ""),
            limit=limit,
        )
        return jsonify(result)

    async def _api_get(self):
        if not self._authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        evidence_id = str(request.args.get("evidence_id", "") or "").strip()
        event = self.store.get(evidence_id)
        if event is None:
            return jsonify({"ok": False, "error": "not_found"}), 404
        return jsonify(
            {
                "ok": True,
                "contract_version": CONTRACT_VERSION,
                "event": event,
            }
        )

    def _authorized(self) -> bool:
        return self._is_loopback_request()

    def _is_loopback_request(self) -> bool:
        forwarded_headers = ("X-Forwarded-For", "X-Real-IP", "Forwarded")
        if any(request.headers.get(name, "").strip() for name in forwarded_headers):
            return False
        remote = str(request.remote_addr or "").strip().lower()
        return remote in {"127.0.0.1", "::1", "localhost"} or remote.startswith("::ffff:127.")

    def _event_origin(self, event: AstrMessageEvent) -> str:
        origin = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if origin:
            return origin
        try:
            return str(event.get_session_id() or "")
        except Exception:  # noqa: BLE001
            return ""

    def _run_startup_maintenance(self) -> None:
        result = self.store.rebuild_index()
        if self.retention_days > 0:
            prune_result = self.store.prune(
                before_ts=int(time.time()) - self.retention_days * 86_400,
                limit=50_000,
                dry_run=False,
            )
            logger.info(
                "Plana Memory Warehouse startup maintenance: indexed=%s pruned=%s",
                result.get("indexed", 0),
                prune_result.get("deleted", 0),
            )
            return
        logger.info(
            "Plana Memory Warehouse startup maintenance: indexed=%s",
            result.get("indexed", 0),
        )



