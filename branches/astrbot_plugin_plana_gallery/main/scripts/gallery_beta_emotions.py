from __future__ import annotations

from collections.abc import Callable
from typing import Any


def check_emotion_profiles(
    store: Any,
    png: bytes,
    require: Callable[[bool, str], None],
) -> None:
    aligned = store.import_bytes(
        png + b"-emotion-aligned",
        filename="emotion-aligned.png",
        caption="兴奋又有点无语",
        tags=["emotion:excited", "emotion:speechless", "intensity:3"],
    )
    require(aligned["ok"], "emotion_profile_import_failed")
    backfilled = aligned["asset"]["emotions"]
    require(
        len(backfilled) == 2
        and all(item["intensity"] == 3 for item in backfilled)
        and sum(item["prominence"] == "primary" for item in backfilled) == 1,
        "emotion_profile_backfill_failed",
    )
    aligned = store.update_asset(
        aligned["asset"]["id"],
        tags=aligned["asset"]["tags"],
        emotions=[
            {
                "emotion_tag": "emotion:excited",
                "intensity": 3,
                "prominence": "primary",
            },
            {
                "emotion_tag": "emotion:speechless",
                "intensity": 1,
                "prominence": "secondary",
            },
        ],
    )
    require(aligned["ok"], "emotion_profile_update_failed")
    require(
        "intensity:3" in aligned["asset"]["tags"]
        and len(aligned["asset"]["emotions"]) == 2,
        "emotion_intensity_projection_failed",
    )

    mismatched = store.import_bytes(
        png + b"-emotion-mismatched",
        filename="emotion-mismatched.png",
        caption="兴奋又有点无语",
        tags=["emotion:excited", "emotion:speechless"],
    )
    require(mismatched["ok"], "mismatched_emotion_import_failed")
    mismatched = store.update_asset(
        mismatched["asset"]["id"],
        tags=mismatched["asset"]["tags"],
        emotions=[
            {
                "emotion_tag": "emotion:excited",
                "intensity": 1,
                "prominence": "secondary",
            },
            {
                "emotion_tag": "emotion:speechless",
                "intensity": 3,
                "prominence": "primary",
            },
        ],
    )
    require(mismatched["ok"], "mismatched_emotion_update_failed")

    emotion_candidates = store.chat_candidates(
        request_id="emotion-ranking:1",
        query="",
        facets=[],
        emotions=[
            {
                "emotion_tag": "emotion:excited",
                "target_intensity": 3,
                "prominence": "primary",
                "weight": 1.2,
            },
            {
                "emotion_tag": "emotion:speechless",
                "target_intensity": 1,
                "prominence": "secondary",
                "weight": 0.8,
            },
        ],
        exclude_asset_refs=[],
        limit=6,
    )
    require(
        emotion_candidates
        and emotion_candidates[0]["asset_ref"] == aligned["asset"]["asset_ref"],
        "emotion_intensity_ranking_failed",
    )
    require(
        set(emotion_candidates[0]["matched_emotions"])
        == {"emotion:excited", "emotion:speechless"}
        and emotion_candidates[0]["score_breakdown"]["intensity_match"] > 0
        and emotion_candidates[0]["score_breakdown"]["primary_alignment"] == 10.0,
        "emotion_score_breakdown_missing",
    )

    conflicting = store.import_bytes(
        png + b"-emotion-conflicting",
        filename="emotion-conflicting.png",
        caption="兴奋但强烈生气",
        tags=["emotion:excited", "emotion:angry"],
    )
    require(conflicting["ok"], "conflicting_emotion_import_failed")
    conflicting = store.update_asset(
        conflicting["asset"]["id"],
        tags=conflicting["asset"]["tags"],
        emotions=[
            {
                "emotion_tag": "emotion:excited",
                "intensity": 3,
                "prominence": "primary",
            },
            {
                "emotion_tag": "emotion:angry",
                "intensity": 3,
                "prominence": "secondary",
            },
        ],
    )
    require(conflicting["ok"], "conflicting_emotion_update_failed")

    conflict_candidates = store.chat_candidates(
        request_id="emotion-conflict:1",
        query="",
        facets=[],
        emotions=[
            {
                "emotion_tag": "emotion:excited",
                "target_intensity": 3,
                "prominence": "primary",
                "weight": 1.0,
            }
        ],
        exclude_asset_refs=[],
        limit=6,
    )
    conflict_row = next(
        row
        for row in conflict_candidates
        if row["asset_ref"] == conflicting["asset"]["asset_ref"]
    )
    aligned_row = next(
        row
        for row in conflict_candidates
        if row["asset_ref"] == aligned["asset"]["asset_ref"]
    )
    require(
        conflict_row["score_breakdown"]["emotion_conflict_penalty"] == -12.0
        and aligned_row["score"] > conflict_row["score"],
        "emotion_conflict_penalty_failed",
    )
