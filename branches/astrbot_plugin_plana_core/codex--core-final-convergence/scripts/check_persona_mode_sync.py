from __future__ import annotations

import sys
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.persona import EmotionVector, PlanaState, PersonaStorage  # noqa: E402
from astrbot_plugin_plana_core.plugin.db import Database  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        storage = PersonaStorage(Database(Path(tmp) / "plana.sqlite3"))
        storage.initialize()

        initial = storage.get_state("global", "standby")
        require(initial.mode == "standby", f"initial_mode={initial.mode}")

        storage.set_state(
            "global",
            PlanaState(
                mode="standby",
                mood_state="calm but alert",
                emotion=EmotionVector(valence=0.7, arousal=0.8, dominance=0.6),
            ),
        )
        updated, changed = storage.ensure_state_mode("global", "observing")
        require(changed, "mode_sync_not_reported")
        require(updated.mode == "observing", f"updated_mode={updated.mode}")
        require(updated.focus == 0.72, f"legacy_focus_default={updated.focus}")
        require(updated.pressure == 0.12, f"legacy_pressure_default={updated.pressure}")
        require(updated.risk_level == "normal", f"legacy_risk_default={updated.risk_level}")
        require(updated.mood_state == "calm but alert", "mood_changed")
        require(updated.emotion.to_dict() == {
            "valence": 0.7,
            "arousal": 0.8,
            "dominance": 0.6,
            "label": "excited",
        }, "emotion_changed")

        reloaded = PersonaStorage(Database(Path(tmp) / "plana.sqlite3"))
        reloaded.initialize()
        persisted = reloaded.get_state("global", "standby")
        require(persisted.emotion.valence == 0.7, "emotion_not_persisted")

        unchanged, changed = storage.ensure_state_mode("global", "observing")
        require(not changed, "mode_sync_should_be_idempotent")
        require(unchanged.mode == "observing", f"unchanged_mode={unchanged.mode}")

        legacy_path = Path(tmp) / "legacy.sqlite3"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.execute(
                """CREATE TABLE persona_states (
                       scope_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                       focus REAL NOT NULL, pressure REAL NOT NULL,
                       risk_level TEXT NOT NULL, mood_state TEXT NOT NULL DEFAULT '',
                       updated_at INTEGER NOT NULL
                   )"""
            )
            conn.execute(
                "INSERT INTO persona_states VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("global", "standby", 0.72, 0.12, "normal", "legacy mood", 1),
            )
            conn.commit()
        finally:
            conn.close()
        legacy = PersonaStorage(Database(legacy_path))
        legacy.initialize()
        migrated = legacy.get_state("global", "standby")
        require(migrated.mood_state == "legacy mood", "legacy_mood_changed")
        require(migrated.emotion.to_dict()["valence"] == 0.3, "legacy_pad_not_defaulted")
        require(migrated.focus == 0.72, "legacy_focus_must_not_reactivate")
        require(migrated.pressure == 0.12, "legacy_pressure_must_not_reactivate")
        require(migrated.risk_level == "normal", "legacy_risk_must_not_reactivate")

    print("persona_mode_sync_check=ok")


if __name__ == "__main__":
    main()
