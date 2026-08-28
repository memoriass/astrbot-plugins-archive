from __future__ import annotations

import json
from time import time
from typing import Any


EXECUTION_STATE_FIELDS = (
    "attempt_id",
    "attempt_no",
    "event_seq",
    "heartbeat_at",
    "lease_expires_at",
    "cancel_requested_at",
    "cancel_acknowledged_at",
    "terminal_at",
)


def merge_execution_state(
    current: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    cancel_requested: bool = False,
    terminal: bool = False,
    now: int | None = None,
) -> dict[str, Any]:
    merged = dict(current or {})
    source = payload if isinstance(payload, dict) else {}
    lifecycle = source.get("execution_state")
    if isinstance(lifecycle, dict):
        source = {**source, **lifecycle}
    for field in EXECUTION_STATE_FIELDS:
        value = source.get(field)
        if field == "attempt_id":
            clean = str(value or "").strip()[:200]
            if clean:
                merged[field] = clean
            continue
        parsed = _positive_int(value)
        if parsed:
            merged[field] = parsed
    timestamp = int(time()) if now is None else int(now)
    if cancel_requested and not merged.get("cancel_requested_at"):
        merged["cancel_requested_at"] = timestamp
    if terminal:
        merged["terminal_at"] = _positive_int(source.get("terminal_at")) or timestamp
        merged["lease_expires_at"] = 0
    return merged


def observation_is_newer(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    current_seq = _positive_int(current.get("event_seq"))
    incoming_seq = _positive_int(incoming.get("event_seq"))
    if incoming_seq:
        return incoming_seq > current_seq
    return any(
        _positive_int(incoming.get(field)) > _positive_int(current.get(field))
        for field in ("heartbeat_at", "cancel_acknowledged_at", "terminal_at")
    )


class RemoteTaskObservationStoreMixin:
    def apply_observation(
        self,
        request_id: str,
        *,
        status: str,
        runner_run_id: str,
        observation: dict[str, Any],
    ) -> str:
        if not request_id:
            return "missing"
        normalized_status = str(status or "running").strip().lower()
        if normalized_status not in {"queued", "submitted", "running", "cancelling"}:
            return "invalid_status"
        now = int(time())
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT status, runner_run_id, execution_state FROM remote_task_runs WHERE request_id=?",
                (request_id[:120],),
            ).fetchone()
            if row is None:
                return "missing"
            current_status = str(row[0] or "")
            if current_status in {"succeeded", "failed", "cancelled", "cancel_failed"}:
                return "ignored_terminal"
            stored_runner = str(row[1] or "")
            if stored_runner and runner_run_id and stored_runner != runner_run_id:
                return "runner_mismatch"
            current_state = self._json(row[2])
            incoming_state = merge_execution_state(current_state, observation, now=now)
            if not observation_is_newer(current_state, incoming_state):
                return "duplicate"
            conn.execute(
                """
                UPDATE remote_task_runs
                SET status=?, runner_run_id=COALESCE(NULLIF(?, ''), runner_run_id),
                    execution_state=?, updated_at=?
                WHERE request_id=?
                """,
                (
                    normalized_status,
                    runner_run_id[:200],
                    json.dumps(incoming_state, ensure_ascii=False, separators=(",", ":"))[:4000],
                    now,
                    request_id[:120],
                ),
            )
        return "applied"


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)
