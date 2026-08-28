from __future__ import annotations

import hashlib
import json
from time import time
from typing import Any


class GalleryDecisionTelemetry:
    def __init__(self, database: Any, retention_days: int = 30) -> None:
        self.database = database
        self.retention_seconds = max(1, int(retention_days)) * 86400
        self._initialize()

    def record(
        self,
        *,
        request_id: str,
        gate_reason: str,
        facets: list[str] | tuple[str, ...] = (),
        emotion_targets: list[dict[str, object]] | tuple[dict[str, object], ...] = (),
        candidate_refs: list[str] | tuple[str, ...] = (),
        selected_ref: str = "",
        selection_method: str = "",
        elapsed_ms: int = 0,
        delivery_result: str = "",
        scope_kind: str = "",
        stage: str = "gated",
        error_category: str = "",
    ) -> None:
        now = int(time())
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO gallery_reaction_decisions (
                    request_id, gate_reason, facets, emotion_targets, candidate_refs, selected_ref,
                    selection_method, elapsed_ms, delivery_result, scope_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    gate_reason=excluded.gate_reason,
                    facets=excluded.facets,
                    emotion_targets=excluded.emotion_targets,
                    candidate_refs=excluded.candidate_refs,
                    selected_ref=excluded.selected_ref,
                    selection_method=excluded.selection_method,
                    elapsed_ms=excluded.elapsed_ms,
                    delivery_result=excluded.delivery_result,
                    scope_kind=excluded.scope_kind,
                    created_at=excluded.created_at
                """,
                (
                    request_id[:160], gate_reason[:120], _json_list(facets, 12),
                    _json_emotions(emotion_targets),
                    _json_list(candidate_refs, 12), selected_ref[:120],
                    selection_method[:80], max(0, int(elapsed_ms)),
                    delivery_result[:120], scope_kind[:40], now,
                ),
            )
            conn.execute(
                "DELETE FROM gallery_reaction_decisions WHERE created_at < ?",
                (now - self.retention_seconds,),
            )
            conn.execute(
                """
                INSERT INTO gallery_reaction_events (
                    request_id, stage, error_category, elapsed_ms, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id[:160], stage[:40], error_category[:40],
                    max(0, int(elapsed_ms)),
                    json.dumps(
                        {
                            "gate_reason": gate_reason[:120],
                            "emotion_targets": json.loads(_json_emotions(emotion_targets)),
                            "selected_ref": selected_ref[:120],
                            "selection_method": selection_method[:80],
                            "delivery_result": delivery_result[:120],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM gallery_reaction_events WHERE created_at < ?",
                (now - self.retention_seconds,),
            )

    def _initialize(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gallery_reaction_decisions (
                    request_id TEXT PRIMARY KEY,
                    gate_reason TEXT NOT NULL DEFAULT '',
                    facets TEXT NOT NULL DEFAULT '[]',
                    emotion_targets TEXT NOT NULL DEFAULT '[]',
                    candidate_refs TEXT NOT NULL DEFAULT '[]',
                    selected_ref TEXT NOT NULL DEFAULT '',
                    selection_method TEXT NOT NULL DEFAULT '',
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    delivery_result TEXT NOT NULL DEFAULT '',
                    scope_kind TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_reaction_created
                    ON gallery_reaction_decisions(created_at DESC);
                CREATE TABLE IF NOT EXISTS gallery_reaction_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    error_category TEXT NOT NULL DEFAULT '',
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_reaction_events_request
                    ON gallery_reaction_events(request_id, id);
                CREATE INDEX IF NOT EXISTS idx_gallery_reaction_events_created
                    ON gallery_reaction_events(created_at DESC);
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(gallery_reaction_decisions)")
            }
            if "emotion_targets" not in columns:
                conn.execute(
                    "ALTER TABLE gallery_reaction_decisions "
                    "ADD COLUMN emotion_targets TEXT NOT NULL DEFAULT '[]'"
                )


class GalleryReactionState:
    def __init__(self, database: Any, retention_days: int = 30) -> None:
        self.database = database
        self.retention_seconds = max(1, int(retention_days)) * 86400
        self._initialize()

    def load(self, cooldown_key: str) -> tuple[float, list[str]]:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT last_sent, recent_refs FROM gallery_reaction_state WHERE scope_hash=?",
                (_scope_hash(cooldown_key),),
            ).fetchone()
        if not row:
            return 0.0, []
        try:
            refs = json.loads(str(row["recent_refs"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            refs = []
        return float(row["last_sent"] or 0), [str(item)[:120] for item in refs[-20:]]

    def mark_delivered(self, cooldown_key: str, asset_ref: str, delivered_at: float) -> None:
        _, recent = self.load(cooldown_key)
        recent = [item for item in recent if item != asset_ref]
        recent.append(asset_ref[:120])
        now = int(time())
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO gallery_reaction_state
                    (scope_hash, last_sent, recent_refs, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_hash) DO UPDATE SET
                    last_sent=excluded.last_sent,
                    recent_refs=excluded.recent_refs,
                    updated_at=excluded.updated_at
                """,
                (
                    _scope_hash(cooldown_key), float(delivered_at),
                    json.dumps(recent[-20:], ensure_ascii=False, separators=(",", ":")), now,
                ),
            )
            conn.execute(
                "DELETE FROM gallery_reaction_state WHERE updated_at < ?",
                (now - self.retention_seconds,),
            )

    def _initialize(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gallery_reaction_state (
                    scope_hash TEXT PRIMARY KEY,
                    last_sent REAL NOT NULL DEFAULT 0,
                    recent_refs TEXT NOT NULL DEFAULT '[]',
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_reaction_state_updated
                    ON gallery_reaction_state(updated_at DESC);
                """
            )


def _json_list(values: list[str] | tuple[str, ...], limit: int) -> str:
    return json.dumps(
        [str(value)[:160] for value in list(values)[:limit]],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_emotions(values: object) -> str:
    result = []
    for item in list(values or [])[:4]:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("emotion_tag") or "")[:80]
        if not tag.startswith("emotion:"):
            continue
        result.append(
            {
                "emotion_tag": tag,
                "target_intensity": max(1, min(int(item.get("target_intensity") or 2), 3)),
                "prominence": (
                    "primary" if item.get("prominence") == "primary" else "secondary"
                ),
                "weight": max(0.0, min(float(item.get("weight") or 0.0), 2.0)),
                "confidence": max(0.0, min(float(item.get("confidence") or 0.0), 1.0)),
            }
        )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _scope_hash(cooldown_key: str) -> str:
    return hashlib.sha256(str(cooldown_key).encode("utf-8")).hexdigest()
