from __future__ import annotations

from dataclasses import dataclass, field
from time import time

# Default mood description — calm, focused state.
_DEFAULT_MOOD = "感觉平静，专注于当前任务"


@dataclass(slots=True)
class EmotionVector:
    """Multi-dimensional emotion model (PAD: Pleasure-Arousal-Dominance).

    Each dimension ranges from -1.0 to 1.0:
    - valence (pleasure): negative=unpleasant, positive=pleasant
    - arousal: low=calm/sleepy, high=excited/alert
    - dominance: low=submissive/controlled, high=dominant/in-control
    """

    valence: float = 0.3
    arousal: float = 0.2
    dominance: float = 0.5

    def normalized(self) -> EmotionVector:
        return EmotionVector(
            valence=min(max(self.valence, -1.0), 1.0),
            arousal=min(max(self.arousal, -1.0), 1.0),
            dominance=min(max(self.dominance, -1.0), 1.0),
        )

    def label(self) -> str:
        """Map PAD values to a human-readable emotion label."""
        v, a, d = self.valence, self.arousal, self.dominance
        if v > 0.3 and a > 0.3:
            return "excited" if d > 0 else "happy"
        if v > 0.3 and a <= 0.3:
            return "relaxed" if d > 0 else "content"
        if v < -0.3 and a > 0.3:
            return "angry" if d > 0 else "anxious"
        if v < -0.3 and a <= 0.3:
            return "sad" if d < 0 else "bored"
        return "neutral"

    def to_dict(self) -> dict[str, float]:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
            "label": self.label(),
        }

    def shift(self, dv: float = 0.0, da: float = 0.0, dd: float = 0.0) -> EmotionVector:
        """Apply a delta shift and return normalized result."""
        return EmotionVector(
            valence=self.valence + dv,
            arousal=self.arousal + da,
            dominance=self.dominance + dd,
        ).normalized()

    def decay_toward_baseline(self, rate: float = 0.05) -> EmotionVector:
        """Gradually decay toward neutral baseline (0.3, 0.2, 0.5)."""
        baseline_v, baseline_a, baseline_d = 0.3, 0.2, 0.5
        return EmotionVector(
            valence=self.valence + (baseline_v - self.valence) * rate,
            arousal=self.arousal + (baseline_a - self.arousal) * rate,
            dominance=self.dominance + (baseline_d - self.dominance) * rate,
        )


@dataclass(slots=True)
class PlanaState:
    mode: str = "standby"
    focus: float = 0.72
    pressure: float = 0.12
    risk_level: str = "normal"
    # Natural-language mood description aligned with NachoBot ChatMood.mood_state.
    # Updated dynamically as interactions accumulate; persisted across restarts.
    mood_state: str = field(default=_DEFAULT_MOOD)
    # Multi-dimensional emotion vector (PAD model)
    emotion: EmotionVector = field(default_factory=EmotionVector)
    updated_at: int = 0

    def normalized(self) -> PlanaState:
        valid_modes = {
            "standby",
            "observing",
            "tasking",
            "checking",
            "risk_review",
            "waiting_confirm",
            "reporting",
            "handoff_to_arona",
            "silent",
        }
        mode = self.mode if self.mode in valid_modes else "standby"
        mood = self.mood_state.strip() if self.mood_state else _DEFAULT_MOOD
        return PlanaState(
            mode=mode,
            focus=min(max(self.focus, 0.0), 1.0),
            pressure=min(max(self.pressure, 0.0), 1.0),
            risk_level=self.risk_level or "normal",
            mood_state=mood or _DEFAULT_MOOD,
            emotion=self.emotion.normalized(),
            updated_at=self.updated_at or int(time()),
        )
