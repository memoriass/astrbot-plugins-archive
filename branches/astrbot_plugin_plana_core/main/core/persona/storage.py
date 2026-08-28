from __future__ import annotations

from ..db import Database
from .models import _DEFAULT_MOOD, PlanaState


class PersonaStorage:
    """Storage for persona states."""

    def __init__(self, db: Database):
        self.db = db

    def initialize(self) -> None:
        """Create persona_states table and migrate schema if needed."""
        with self.db.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS persona_states (
                    scope_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    focus REAL NOT NULL,
                    pressure REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    mood_state TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );
                """
            )
            # Migrate: add mood_state column if the table already existed without it.
            cols = {row[1] for row in conn.execute("PRAGMA table_info(persona_states)")}
            if "mood_state" not in cols:
                conn.execute(
                    "ALTER TABLE persona_states ADD COLUMN mood_state TEXT NOT NULL DEFAULT ''"
                )

    def get_state(self, scope_id: str, default_mode: str) -> PlanaState:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT mode, focus, pressure, risk_level, mood_state, updated_at"
                " FROM persona_states WHERE scope_id=?",
                (scope_id,),
            ).fetchone()
        if not row:
            state = PlanaState(mode=default_mode).normalized()
            self.set_state(scope_id, state)
            return state
        return PlanaState(
            mode=row[0],
            focus=row[1],
            pressure=row[2],
            risk_level=row[3],
            mood_state=row[4] or _DEFAULT_MOOD,
            updated_at=row[5],
        ).normalized()

    def set_state(self, scope_id: str, state: PlanaState) -> None:
        state = state.normalized()
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO persona_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope_id,
                    state.mode,
                    state.focus,
                    state.pressure,
                    state.risk_level,
                    state.mood_state,
                    state.updated_at,
                ),
            )
