from __future__ import annotations

import threading
import time
from typing import Any


RUNNER_HEARTBEAT_INTERVAL_SECONDS = 5
RUNNER_LEASE_SECONDS = 20


class RunnerLifecycleMixin:
    def _initialize_lifecycle_columns(self, conn: Any) -> None:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(codex_runs)").fetchall()
        }
        declarations = {
            "attempt_id": "TEXT NOT NULL DEFAULT ''",
            "event_seq": "INTEGER NOT NULL DEFAULT 0",
            "heartbeat_at": "INTEGER NOT NULL DEFAULT 0",
            "lease_expires_at": "INTEGER NOT NULL DEFAULT 0",
            "cancel_requested_at": "INTEGER NOT NULL DEFAULT 0",
            "cancel_acknowledged_at": "INTEGER NOT NULL DEFAULT 0",
            "terminal_at": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, declaration in declarations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE codex_runs ADD COLUMN {column} {declaration}")

    def _start_lifecycle_heartbeat(self, run_id: str) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()
        worker = threading.Thread(
            target=self._lifecycle_heartbeat_loop,
            args=(run_id, stop),
            name=f"plana-codex-heartbeat-{run_id[-12:]}",
            daemon=True,
        )
        worker.start()
        return stop, worker

    def _lifecycle_heartbeat_loop(self, run_id: str, stop: threading.Event) -> None:
        while not stop.wait(RUNNER_HEARTBEAT_INTERVAL_SECONDS):
            now = int(time.time())
            with self.lock, self._connect() as conn:
                affected = conn.execute(
                    """
                    UPDATE codex_runs
                    SET heartbeat_at=?, lease_expires_at=?, event_seq=event_seq+1,
                        updated_at=?
                    WHERE run_id=? AND status IN ('running', 'cancelling')
                    """,
                    (now, now + RUNNER_LEASE_SECONDS, now, run_id),
                ).rowcount
            if not affected:
                return

    def _lifecycle_snapshot(self, run_id: str) -> dict[str, Any]:
        with self.lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT attempt_id, attempts, event_seq, heartbeat_at, lease_expires_at,
                       cancel_requested_at, cancel_acknowledged_at, terminal_at
                FROM codex_runs WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return {}
        return {
            "attempt_id": str(row[0] or ""),
            "attempt_no": int(row[1] or 0),
            "event_seq": int(row[2] or 0),
            "heartbeat_at": int(row[3] or 0),
            "lease_expires_at": int(row[4] or 0),
            "cancel_requested_at": int(row[5] or 0),
            "cancel_acknowledged_at": int(row[6] or 0),
            "terminal_at": int(row[7] or 0),
        }
