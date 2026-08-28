from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import time
from typing import Any


@dataclass(slots=True)
class SocialInteractionState:
    scope_id: str
    actor_id: str
    familiarity: float = 0.2
    evidence_confidence: float = 0.2
    successful_tasks: int = 0
    failed_tasks: int = 0
    participation_tolerance: float = 0.35
    interruption_tolerance: float = 0.25
    correction_tolerance: float = 0.5
    preferred_address: str = ""
    preferred_density: str = "balanced"
    interaction_trend: float = 0.0
    evidence_version: int = 1
    updated_at: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SocialInteractionStore:
    """Core-owned social policy state; never an authorization source."""

    def __init__(self, database: Any | None) -> None:
        self._database = database
        self._cache: dict[tuple[str, str], SocialInteractionState] = {}
        self._initialize()

    def get(self, scope_id: str, actor_id: str) -> SocialInteractionState:
        key = (scope_id or "global", actor_id or "user")
        if key not in self._cache:
            self._cache[key] = self._load(*key) or SocialInteractionState(*key)
        return self._cache[key]

    def record_outcome(self, scope_id: str, actor_id: str, *, success: bool) -> None:
        state = self.get(scope_id, actor_id)
        if success:
            state.successful_tasks += 1
            state.familiarity = min(0.9, state.familiarity + 0.01)
            state.interaction_trend = min(1.0, state.interaction_trend + 0.03)
        else:
            state.failed_tasks += 1
            state.interaction_trend = max(-1.0, state.interaction_trend - 0.12)
        state.evidence_confidence = min(0.95, state.evidence_confidence + 0.01)
        state.updated_at = int(time())
        self._save(state)

    def record_feedback(self, scope_id: str, actor_id: str, text: str) -> None:
        clean = " ".join(str(text or "").lower().split())
        state = self.get(scope_id, actor_id)
        if any(marker in clean for marker in ("别插话", "安静", "不要主动", "没问你")):
            state.participation_tolerance = max(0.0, state.participation_tolerance - 0.35)
            state.interruption_tolerance = max(0.0, state.interruption_tolerance - 0.35)
            state.interaction_trend = max(-1.0, state.interaction_trend - 0.3)
        elif any(marker in clean for marker in ("可以主动", "提醒我", "你看着办", "做得好", "谢谢")):
            state.participation_tolerance = min(0.8, state.participation_tolerance + 0.04)
            state.interaction_trend = min(1.0, state.interaction_trend + 0.05)
        else:
            return
        state.updated_at = int(time())
        self._save(state)

    def _initialize(self) -> None:
        if self._database is None:
            return
        with self._database.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS assistant_social_states (scope_id TEXT NOT NULL, actor_id TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL, PRIMARY KEY(scope_id, actor_id))")

    def _load(self, scope_id: str, actor_id: str) -> SocialInteractionState | None:
        if self._database is None:
            return None
        with self._database.connect() as conn:
            row = conn.execute("SELECT payload FROM assistant_social_states WHERE scope_id=? AND actor_id=?", (scope_id[:200], actor_id[:200])).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload"] or "{}"))
            allowed = SocialInteractionState.__dataclass_fields__.keys()
            values = {key: payload[key] for key in allowed if key in payload}
            values.update(scope_id=scope_id, actor_id=actor_id)
            return SocialInteractionState(**values)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def _save(self, state: SocialInteractionState) -> None:
        self._cache[(state.scope_id, state.actor_id)] = state
        if self._database is None:
            return
        payload = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._database.connect() as conn:
            conn.execute("INSERT INTO assistant_social_states(scope_id, actor_id, payload, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(scope_id, actor_id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at", (state.scope_id[:200], state.actor_id[:200], payload, state.updated_at))
