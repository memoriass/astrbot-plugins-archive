from __future__ import annotations

from collections import deque
import json
from dataclasses import asdict, dataclass, field
from threading import RLock
from time import time
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class TaskRouteTrace:
    scope_id: str
    actor_id: str
    text: str
    wake_source: str = ""
    preflight_source: str = ""
    preflight_reason: str = ""
    route: str = ""
    intent: str = ""
    action: str = ""
    capability: str = ""
    status: str = ""
    run_id: int | None = None
    sandbox: str = ""
    reason: str = ""
    recovery: str = ""
    expected_capability: str = ""
    remote_reason: str = ""
    reuse_match: dict[str, Any] | None = None
    tool_profile: str = ""
    risk_class: str = ""
    artifact_count: int = 0
    clarification_count: int = 0
    created_at: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["text"] = self.text[:240]
        return data


@dataclass(slots=True)
class TaskSessionState:
    scope_id: str
    actor_id: str
    latest_pending_run_id: int | None = None
    latest_prompt: str = ""
    latest_route: str = ""
    latest_failure: str = ""
    latest_recovery: str = ""
    latest_expected_capability: str = ""
    latest_llm_tool_pending: bool = False
    latest_remote_authorization_pending: bool = False
    latest_remote_lane: str = "interactive"
    latest_remote_reason: str = ""
    latest_execution_context_id: str = ""
    latest_service_ref: str = ""
    latest_remote_request_id: str = ""
    latest_result_summary: str = ""
    latest_artifact_path: str = ""
    latest_artifact_name: str = ""
    latest_artifact_mime: str = ""
    latest_artifact_summary: str = ""
    latest_artifact_ref: dict[str, Any] = field(default_factory=dict)
    current_goal: str = ""
    focus_stack: list[dict[str, Any]] = field(default_factory=list)
    active_tasks: list[dict[str, Any]] = field(default_factory=list)
    latest_result: dict[str, Any] = field(default_factory=dict)
    pending_disambiguation: list[dict[str, Any]] = field(default_factory=list)
    local_failure_count: int = 0
    revision: int = 0
    pending_action_token: str = ""
    pending_action_kind: str = ""
    pending_action_started_at: float = 0.0
    updated_at: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskSessionStore:
    """Short-lived conversational task state backed by Core SQLite.

    This is operational continuation state, not durable personal memory. The
    database copy only exists so short follow-ups and cancellation survive an
    AstrBot process restart.
    """

    def __init__(
        self,
        database: Any | None = None,
        *,
        max_traces: int = 80,
        ttl_seconds: int = 180,
    ) -> None:
        self._database = database
        self._ttl_seconds = max(30, min(int(ttl_seconds or 180), 3600))
        self._action_claim_ttl_seconds = self._ttl_seconds
        self._sessions: dict[tuple[str, str], TaskSessionState] = {}
        self._traces: deque[TaskRouteTrace] = deque(maxlen=max(8, max_traces))
        self._locks: dict[tuple[str, str], RLock] = {}
        self._locks_guard = RLock()
        self._active_action_tokens: set[str] = set()
        self._initialize()

    def session(self, scope_id: str, actor_id: str) -> TaskSessionState:
        key = (scope_id or "global", actor_id or "user")
        with self._lock_for(key):
            state = self._sessions.get(key)
            if state is None:
                state = self._load(key[0], key[1]) or TaskSessionState(
                    scope_id=key[0], actor_id=key[1]
                )
                self._sessions[key] = state
            return state

    def claim_action(self, scope_id: str, actor_id: str, kind: str) -> str:
        key = (scope_id or "global", actor_id or "user")
        with self._lock_for(key):
            for _ in range(2):
                state = self._load(key[0], key[1]) or self._sessions.get(key)
                if state is None:
                    state = TaskSessionState(scope_id=key[0], actor_id=key[1])
                now = time()
                if state.pending_action_token:
                    active_here = state.pending_action_token in self._active_action_tokens
                    claim_age = now - float(state.pending_action_started_at or 0.0)
                    if active_here or claim_age < self._action_claim_ttl_seconds:
                        self._sessions[key] = state
                        return ""
                token = uuid4().hex
                state.pending_action_token = token
                state.pending_action_kind = str(kind or "natural_action")[:80]
                state.pending_action_started_at = now
                state.updated_at = now
                if self.persist(state):
                    self._active_action_tokens.add(token)
                    return token
            return ""

    def release_action(self, scope_id: str, actor_id: str, token: str) -> bool:
        if not token:
            return False
        key = (scope_id or "global", actor_id or "user")
        with self._lock_for(key):
            try:
                for _ in range(2):
                    state = self._load(key[0], key[1]) or self._sessions.get(key)
                    if state is None or state.pending_action_token != token:
                        return False
                    state.pending_action_token = ""
                    state.pending_action_kind = ""
                    state.pending_action_started_at = 0.0
                    state.updated_at = time()
                    if self.persist(state):
                        return True
                return False
            finally:
                self._active_action_tokens.discard(token)

    def record_trace(self, trace: TaskRouteTrace) -> None:
        self._traces.appendleft(trace)
        state = self.session(trace.scope_id, trace.actor_id)
        state.latest_prompt = trace.text[:500]
        state.current_goal = trace.text[:500]
        state.latest_route = trace.route
        state.latest_expected_capability = trace.expected_capability or trace.capability
        state.updated_at = trace.created_at
        if trace.run_id and trace.status == "waiting_confirm":
            state.latest_pending_run_id = trace.run_id
        if trace.status == "pass_to_llm":
            state.latest_llm_tool_pending = True
        if trace.recovery or trace.status in {"failed", "rejected"}:
            state.latest_failure = trace.reason
            state.latest_recovery = trace.recovery
            state.local_failure_count += 1
        if trace.status in {"completed", "remote_queued"}:
            state.local_failure_count = 0
        self.persist(state)

    def clear_pending(self, scope_id: str, actor_id: str, run_id: int | None = None) -> None:
        key = (scope_id or "global", actor_id or "user")
        with self._lock_for(key):
            for _ in range(2):
                state = self._load(key[0], key[1]) or self._sessions.get(key)
                if state is None:
                    return
                if run_id is not None and state.latest_pending_run_id != run_id:
                    return
                state.latest_pending_run_id = None
                state.updated_at = time()
                if self.persist(state):
                    return

    def record_artifact(
        self,
        scope_id: str,
        actor_id: str,
        *,
        path: str,
        name: str = "",
        mime_type: str = "image/png",
        summary: str = "",
        recipients: tuple[str, ...] = (),
        ttl_seconds: int = 86400,
    ) -> None:
        from ..presentation.artifacts import artifact_reference

        state = self.session(scope_id, actor_id)
        state.latest_artifact_path = str(path or "")[:1000]
        state.latest_artifact_name = str(name or "")[:240]
        state.latest_artifact_mime = str(mime_type or "")[:120]
        state.latest_artifact_summary = str(summary or "")[:500]
        state.latest_artifact_ref = artifact_reference(
            path,
            name=name,
            mime_type=mime_type,
            recipients=recipients or (actor_id,),
            ttl_seconds=ttl_seconds,
        ).to_dict()
        state.updated_at = time()
        self.persist(state)

    def latest_pending_for_scope(self, scope_id: str) -> int | None:
        scope = scope_id or "global"
        candidates = [
            state
            for state in self._sessions.values()
            if state.scope_id == scope and state.latest_pending_run_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item.updated_at, reverse=True)
        return candidates[0].latest_pending_run_id

    def push_focus(self, scope_id: str, actor_id: str, *, topic: str, capability: str = "", resource_refs: list[str] | tuple[str, ...] = (), task_id: str = "") -> None:
        state = self.session(scope_id, actor_id)
        item = {"topic": str(topic or "")[:500], "capability": str(capability or "")[:160], "resource_refs": [str(value)[:240] for value in resource_refs[:16]], "task_id": str(task_id or "")[:200], "updated_at": int(time())}
        state.focus_stack = [item, *state.focus_stack[:7]]
        state.current_goal = item["topic"]
        state.updated_at = time()
        self.persist(state)

    def status(self) -> dict[str, Any]:
        return {
            "sessions": [state.to_dict() for state in self._sessions.values()],
            "recent_traces": [trace.to_dict() for trace in self._traces],
        }

    def recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        return [trace.to_dict() for trace in list(self._traces)[: max(1, limit)]]

    def persist(self, state: TaskSessionState) -> bool:
        key = (state.scope_id or "global", state.actor_id or "user")
        with self._lock_for(key):
            if self._database is None:
                state.revision = max(0, int(state.revision or 0)) + 1
                self._sessions[key] = state
                return True
            with self._database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT payload, updated_at
                    FROM assistant_conversation_frames
                    WHERE scope_id=? AND actor_id=?
                    """,
                    (key[0][:200], key[1][:200]),
                ).fetchone()
                row_is_expired = (
                    row is not None
                    and int(row["updated_at"] or 0) < int(time()) - self._ttl_seconds
                )
                current = (
                    None
                    if row_is_expired
                    else self._state_from_row(row, key[0], key[1])
                )
                current_revision = int(current.revision or 0) if current else 0
                if current is not None and current_revision > int(state.revision or 0):
                    self._sessions[key] = current
                    conn.execute(
                        "DELETE FROM assistant_conversation_frames WHERE updated_at < ?",
                        (int(time()) - self._ttl_seconds,),
                    )
                    return False
                state.scope_id = key[0]
                state.actor_id = key[1]
                state.revision = current_revision + 1
                payload = json.dumps(
                    state.to_dict(), ensure_ascii=False, separators=(",", ":")
                )
                conn.execute(
                    """
                    INSERT INTO assistant_conversation_frames (
                        scope_id, actor_id, payload, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(scope_id, actor_id) DO UPDATE SET
                        payload=excluded.payload,
                        updated_at=excluded.updated_at
                    """,
                    (key[0][:200], key[1][:200], payload, int(state.updated_at)),
                )
                conn.execute(
                    "DELETE FROM assistant_conversation_frames WHERE updated_at < ?",
                    (int(time()) - self._ttl_seconds,),
                )
            self._sessions[key] = state
            return True

    def _initialize(self) -> None:
        if self._database is None:
            return
        with self._database.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_conversation_frames (
                    scope_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(scope_id, actor_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assistant_frames_updated_at "
                "ON assistant_conversation_frames(updated_at)"
            )

    def _load(self, scope_id: str, actor_id: str) -> TaskSessionState | None:
        if self._database is None:
            return None
        with self._database.connect() as conn:
            row = conn.execute(
                """
                SELECT payload, updated_at
                FROM assistant_conversation_frames
                WHERE scope_id=? AND actor_id=?
                """,
                (scope_id[:200], actor_id[:200]),
            ).fetchone()
        if row is None or int(row["updated_at"] or 0) < int(time()) - self._ttl_seconds:
            return None
        return self._state_from_row(row, scope_id, actor_id)

    def _state_from_row(
        self,
        row: Any,
        scope_id: str,
        actor_id: str,
    ) -> TaskSessionState | None:
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        allowed = TaskSessionState.__dataclass_fields__.keys()
        values = {key: payload[key] for key in allowed if key in payload}
        values["scope_id"] = scope_id
        values["actor_id"] = actor_id
        try:
            return TaskSessionState(**values)
        except (TypeError, ValueError):
            return None

    def _lock_for(self, key: tuple[str, str]) -> RLock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = RLock()
                self._locks[key] = lock
            return lock
