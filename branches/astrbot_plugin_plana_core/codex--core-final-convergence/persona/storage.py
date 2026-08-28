from __future__ import annotations

from ..plugin.db import Database
from .models import _DEFAULT_MOOD, EmotionVector, PlanaState


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
                    emotion_valence REAL NOT NULL DEFAULT 0.3,
                    emotion_arousal REAL NOT NULL DEFAULT 0.2,
                    emotion_dominance REAL NOT NULL DEFAULT 0.5,
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
            for column, default in (
                ("emotion_valence", "0.3"),
                ("emotion_arousal", "0.2"),
                ("emotion_dominance", "0.5"),
            ):
                if column not in cols:
                    conn.execute(
                        f"ALTER TABLE persona_states ADD COLUMN {column} "
                        f"REAL NOT NULL DEFAULT {default}"
                    )

    def get_state(self, scope_id: str, default_mode: str) -> PlanaState:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT mode, mood_state, emotion_valence, emotion_arousal, "
                "emotion_dominance, updated_at"
                " FROM persona_states WHERE scope_id=?",
                (scope_id,),
            ).fetchone()
        if not row:
            state = PlanaState(mode=default_mode).normalized()
            self.set_state(scope_id, state)
            return state
        return PlanaState(
            mode=row[0],
            mood_state=row[1] or _DEFAULT_MOOD,
            emotion=EmotionVector(
                valence=float(row[2]),
                arousal=float(row[3]),
                dominance=float(row[4]),
            ),
            updated_at=row[5],
        ).normalized()

    def ensure_state_mode(
        self,
        scope_id: str,
        mode: str,
        default_mode: str | None = None,
    ) -> tuple[PlanaState, bool]:
        current = self.get_state(scope_id, default_mode or mode)
        desired_mode = PlanaState(mode=mode).normalized().mode
        if current.mode == desired_mode:
            return current, False
        updated = PlanaState(
            mode=desired_mode,
            mood_state=current.mood_state,
            emotion=current.emotion,
        ).normalized()
        self.set_state(scope_id, updated)
        return updated, True

    def set_state(self, scope_id: str, state: PlanaState) -> None:
        state = state.normalized()
        with self.db.connect() as conn:
            conn.execute(
                """INSERT INTO persona_states (
                       scope_id, mode, focus, pressure, risk_level, mood_state,
                       emotion_valence, emotion_arousal, emotion_dominance, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope_id) DO UPDATE SET
                       mode=excluded.mode,
                       mood_state=excluded.mood_state,
                       emotion_valence=excluded.emotion_valence,
                       emotion_arousal=excluded.emotion_arousal,
                       emotion_dominance=excluded.emotion_dominance,
                       updated_at=excluded.updated_at""",
                (
                    scope_id,
                    state.mode,
                    0.72,
                    0.12,
                    "normal",
                    state.mood_state,
                    state.emotion.valence,
                    state.emotion.arousal,
                    state.emotion.dominance,
                    state.updated_at,
                ),
            )
