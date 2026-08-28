from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from typing import Any


TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


class DeliveryIdempotencyLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS bridge_delivery_ledger (
                       idempotency_key TEXT PRIMARY KEY,
                       terminal_status TEXT NOT NULL,
                       payload_digest TEXT NOT NULL,
                       notification_sent INTEGER NOT NULL DEFAULT 0,
                       updated_at INTEGER NOT NULL
                   )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS bridge_delivery_phases (
                       idempotency_key TEXT NOT NULL,
                       phase TEXT NOT NULL,
                       status TEXT NOT NULL,
                       payload_digest TEXT NOT NULL,
                       updated_at INTEGER NOT NULL,
                       PRIMARY KEY(idempotency_key, phase)
                   )"""
            )
            conn.commit()

    def terminal(self, key: str) -> dict[str, Any] | None:
        clean_key = self._key(key)
        if not clean_key:
            return None
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM bridge_delivery_ledger WHERE idempotency_key=?",
                (clean_key,),
            ).fetchone()
        return dict(row) if row else None

    def record_phase(
        self,
        key: str,
        phase: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        clean_key = self._key(key)
        clean_phase = str(phase or "").strip().lower()
        clean_status = str(status or "").strip().lower()
        if not clean_key or clean_phase not in {
            "submit", "poll", "callback", "artifact", "terminal", "notification"
        } or clean_status not in {"pending", "succeeded", "failed", "skipped"}:
            return {"ok": False, "error": "invalid_phase_envelope"}
        digest = self.payload_digest(payload)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                """SELECT * FROM bridge_delivery_phases
                   WHERE idempotency_key=? AND phase=?""",
                (clean_key, clean_phase),
            ).fetchone()
            if existing:
                same = existing["status"] == clean_status and existing["payload_digest"] == digest
                return {"ok": same, "replay": same, "conflict": not same}
            conn.execute(
                """INSERT INTO bridge_delivery_phases
                   (idempotency_key, phase, status, payload_digest, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (clean_key, clean_phase, clean_status, digest, int(time.time())),
            )
            conn.commit()
        return {"ok": True, "replay": False, "conflict": False}

    def phases(self, key: str) -> list[dict[str, Any]]:
        clean_key = self._key(key)
        if not clean_key:
            return []
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM bridge_delivery_phases
                   WHERE idempotency_key=? ORDER BY updated_at, phase""",
                (clean_key,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_terminal(
        self,
        key: str,
        status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        clean_key = self._key(key)
        clean_status = str(status or "").strip().lower()
        if not clean_key or clean_status not in TERMINAL_STATES:
            return {"ok": False, "error": "invalid_terminal_envelope"}
        digest = self.payload_digest(payload)
        existing = self.terminal(clean_key)
        if existing:
            same = (
                existing["terminal_status"] == clean_status
                and existing["payload_digest"] == digest
            )
            return {
                "ok": same,
                "replay": same,
                "conflict": not same,
                "status": existing["terminal_status"],
                "notification_sent": bool(existing["notification_sent"]),
            }
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """INSERT INTO bridge_delivery_ledger
                   (idempotency_key, terminal_status, payload_digest, notification_sent, updated_at)
                   VALUES (?, ?, ?, 0, ?)""",
                (clean_key, clean_status, digest, int(time.time())),
            )
            conn.commit()
        return {
            "ok": True,
            "replay": False,
            "conflict": False,
            "status": clean_status,
            "notification_sent": False,
        }

    def mark_notification_sent(self, key: str) -> bool:
        clean_key = self._key(key)
        if not clean_key:
            return False
        with closing(sqlite3.connect(self.path)) as conn:
            changed = conn.execute(
                """UPDATE bridge_delivery_ledger
                   SET notification_sent=1, updated_at=?
                   WHERE idempotency_key=? AND notification_sent=0""",
                (int(time.time()), clean_key),
            ).rowcount
            conn.commit()
        return bool(changed)

    @staticmethod
    def payload_digest(payload: dict[str, Any]) -> str:
        bounded = {
            "request_id": str(payload.get("request_id") or ""),
            "runner_run_id": str(payload.get("runner_run_id") or payload.get("run_id") or ""),
            "status": str(payload.get("status") or ""),
            "success": bool(payload.get("success", False)),
            "summary": str(payload.get("result_summary") or payload.get("summary") or "")[:4000],
            "error": str(payload.get("error") or "")[:1000],
            "artifacts": payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
        }
        raw = json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _key(value: str) -> str:
        clean = str(value or "").strip()
        if not clean or len(clean) > 240:
            return ""
        return clean
