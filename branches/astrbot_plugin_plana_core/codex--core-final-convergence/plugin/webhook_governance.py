from __future__ import annotations

import inspect
import json
import secrets
from time import time
from typing import Any

from .sibling_services import find_sibling_service


WEBHOOK_PLUGIN_NAME = "astrbot_plugin_webhook_push"
CONTRACT_VERSION = "plana.webhook.event.v1"
VALID_SOURCES = frozenset({"media", "game", "common"})
VALID_ACTIONS = frozenset({"deliver", "ignore", "delay", "aggregate"})


class WebhookGovernanceService:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.db = runtime.storage.db

    def initialize(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS webhook_policies (
                    source TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    action TEXT NOT NULL DEFAULT 'deliver',
                    target TEXT NOT NULL DEFAULT '',
                    template TEXT NOT NULL DEFAULT '',
                    aggregate_seconds INTEGER NOT NULL DEFAULT 0,
                    updated_by TEXT NOT NULL DEFAULT 'system',
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    payload_ref TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '',
                    template TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'pending',
                    message_id TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    fallback INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_webhook_events_recent
                    ON webhook_events(updated_at DESC);
                """
            )
            now = int(time())
            for source in sorted(VALID_SOURCES):
                conn.execute(
                    "INSERT OR IGNORE INTO webhook_policies(source, updated_at) VALUES(?, ?)",
                    (source, now),
                )
            conn.commit()

    def evaluate_event(self, event: dict[str, Any], *, core_token: str = "") -> dict[str, Any]:
        self._require_authorized(core_token)
        valid, error = self._validate_event(event)
        if not valid:
            raise ValueError(error)
        source = str(event["source"])
        policy = self.policy(source)
        now = int(time())
        with self.db.connect() as conn:
            duplicate = conn.execute(
                "SELECT event_id FROM webhook_events WHERE dedupe_key=?",
                (str(event["dedupe_key"]),),
            ).fetchone()
            action = "ignore" if duplicate else str(policy["action"])
            reason = "duplicate_event" if duplicate else "policy_applied"
            if not bool(policy["enabled"]):
                action, reason = "ignore", "source_disabled"
            conn.execute(
                """INSERT OR IGNORE INTO webhook_events(
                       event_id, source, event_type, dedupe_key, payload_ref, summary,
                       target, template, status, delivery_status, created_at, updated_at
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    str(event["event_id"]), source, str(event["event_type"]),
                    str(event["dedupe_key"]), str(event["payload_ref"]), str(event["summary"]),
                    str(event.get("target") or ""), str(event.get("template") or ""),
                    "ignored" if action == "ignore" else "accepted", now, now,
                ),
            )
            conn.commit()
        return {
            "action": action,
            "target": str(policy["target"] or event.get("target") or ""),
            "template": str(policy["template"] or event.get("template") or ""),
            "aggregate_seconds": int(policy["aggregate_seconds"]),
            "reason": reason,
        }

    def record_delivery(
        self,
        event_id: str,
        delivery_status: str,
        *,
        core_token: str = "",
        message_id: str = "",
        error: str = "",
        updated_at: int = 0,
    ) -> None:
        self._require_authorized(core_token)
        with self.db.connect() as conn:
            conn.execute(
                """UPDATE webhook_events
                   SET delivery_status=?, message_id=?, error=?, updated_at=?
                   WHERE event_id=?""",
                (
                    str(delivery_status or "unknown")[:40],
                    str(message_id or "")[:160],
                    str(error or "")[:200],
                    int(updated_at or time()),
                    str(event_id or ""),
                ),
            )
            conn.commit()

    def status(self) -> dict[str, Any]:
        companion = self._companion()
        companion_status = (
            companion.status(core_token=self._core_service_key())
            if companion is not None
            else {"ok": False}
        )
        with self.db.connect() as conn:
            counts = conn.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN delivery_status='delivered' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN delivery_status='failed' THEN 1 ELSE 0 END)
                   FROM webhook_events"""
            ).fetchone()
        return {
            "ok": bool(companion_status.get("ok")),
            "plugin": WEBHOOK_PLUGIN_NAME,
            "companion": companion_status,
            "events": int(counts[0] or 0),
            "delivered": int(counts[1] or 0),
            "failed": int(counts[2] or 0),
        }

    def sources(self) -> dict[str, Any]:
        companion = self._companion()
        live = (
            companion.sources(core_token=self._core_service_key())
            if companion is not None
            else {"ok": False, "sources": []}
        )
        live_by_source = {
            str(item.get("source") or ""): item
            for item in live.get("sources", [])
            if isinstance(item, dict)
        }
        return {
            "ok": bool(live.get("ok")),
            "sources": [
                {**live_by_source.get(source, {"source": source, "enabled": False, "routes": []}), "policy": self.policy(source)}
                for source in sorted(VALID_SOURCES)
            ],
        }

    def events(self, limit: int = 50) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self.db.connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = conn.execute(
                "SELECT * FROM webhook_events ORDER BY updated_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return {"ok": True, "events": [dict(row) for row in rows]}

    def policy(self, source: str) -> dict[str, Any]:
        clean_source = self._source(source)
        with self.db.connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            row = conn.execute(
                "SELECT * FROM webhook_policies WHERE source=?",
                (clean_source,),
            ).fetchone()
        return dict(row) if row else {
            "source": clean_source,
            "enabled": 1,
            "action": "deliver",
            "target": "",
            "template": "",
            "aggregate_seconds": 0,
        }

    def update_policy(self, source: str, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        try:
            clean_source = self._source(source)
        except ValueError:
            return {"ok": False, "error": "invalid_source"}
        current = self.policy(clean_source)
        action = str(values.get("action", current["action"]) or "deliver").strip()
        if action not in VALID_ACTIONS:
            return {"ok": False, "error": "invalid_action"}
        target = str(values.get("target", current["target"]) or "").strip()[:120]
        template = str(values.get("template", current["template"]) or "").strip()[:120]
        companion = self._companion()
        if template and companion is not None:
            live_sources = companion.sources(core_token=self._core_service_key())
            if not live_sources.get("ok"):
                return {"ok": False, "error": str(live_sources.get("error") or "webhook_companion_unavailable")}
            templates = {
                str(item.get("template") or "")
                for item in live_sources.get("sources", [])
                if isinstance(item, dict)
            }
            if template not in templates:
                return {"ok": False, "error": "template_not_registered"}
        enabled = 1 if bool(values.get("enabled", current["enabled"])) else 0
        aggregate_seconds = max(0, min(int(values.get("aggregate_seconds", current["aggregate_seconds"]) or 0), 86400))
        now = int(time())
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO webhook_policies(
                       source, enabled, action, target, template, aggregate_seconds, updated_by, updated_at
                   ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source) DO UPDATE SET
                       enabled=excluded.enabled, action=excluded.action, target=excluded.target,
                       template=excluded.template, aggregate_seconds=excluded.aggregate_seconds,
                       updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (clean_source, enabled, action, target, template, aggregate_seconds, str(actor or "system")[:120], now),
            )
            conn.commit()
        return {"ok": True, "policy": self.policy(clean_source)}

    async def replay(self, event_id: str) -> dict[str, Any]:
        clean_id = str(event_id or "").strip()
        companion = self._companion()
        if companion is None:
            return {"ok": False, "error": "webhook_companion_unavailable"}
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT delivery_status FROM webhook_events WHERE event_id=?",
                (clean_id,),
            ).fetchone()
            if row is None:
                return {"ok": False, "error": "event_not_found"}
            if str(row[0]) not in {"failed", "render_failed"}:
                return {"ok": False, "error": "event_not_replayable"}
            conn.execute(
                "UPDATE webhook_events SET delivery_status='replay_requested', updated_at=? WHERE event_id=?",
                (int(time()), clean_id),
            )
            conn.commit()
        result = companion.replay(clean_id, core_token=self._core_service_key())
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict) or not result.get("ok"):
            self.record_delivery(
                clean_id,
                "failed",
                core_token=self._core_service_key(),
                error=str((result or {}).get("error") if isinstance(result, dict) else "replay_failed"),
            )
            return result if isinstance(result, dict) else {"ok": False, "error": "replay_failed"}
        return result

    def _companion(self) -> Any | None:
        return find_sibling_service(
            self.runtime,
            plugin_name=WEBHOOK_PLUGIN_NAME,
            service_attr="core_service",
            required_methods=("status", "sources", "recent_events", "replay"),
        )

    def _core_service_key(self) -> str:
        return str(self.runtime.config.get("plana_core_service_key", "") or "").strip()

    def _require_authorized(self, core_token: str) -> None:
        expected = self._core_service_key()
        supplied = str(core_token or "").strip()
        if not expected or not supplied or not secrets.compare_digest(supplied, expected):
            raise PermissionError("core_service_unauthorized")

    @staticmethod
    def _source(source: str) -> str:
        clean_source = str(source or "").strip().lower()
        if clean_source not in VALID_SOURCES:
            raise ValueError("invalid_source")
        return clean_source

    @staticmethod
    def _validate_event(event: dict[str, Any]) -> tuple[bool, str]:
        if not isinstance(event, dict) or event.get("contract_version") != CONTRACT_VERSION:
            return False, "invalid_contract"
        for key in ("event_id", "source", "event_type", "dedupe_key", "payload_ref", "summary"):
            if not str(event.get(key) or "").strip():
                return False, f"missing_{key}"
        if str(event.get("source")) not in VALID_SOURCES:
            return False, "invalid_source"
        if not str(event.get("payload_ref")).startswith("sha256:"):
            return False, "invalid_payload_ref"
        try:
            json.dumps(event, ensure_ascii=False)
        except (TypeError, ValueError):
            return False, "event_not_serializable"
        return True, ""
