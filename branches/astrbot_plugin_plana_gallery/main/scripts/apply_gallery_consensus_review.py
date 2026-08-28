from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "scripts"))

from astrbot_plugin_plana_gallery.assets.constants import REVIEW_TAG  # noqa: E402
from astrbot_plugin_plana_gallery.assets.store import GalleryStore  # noqa: E402
from apply_gallery_visual_classification import EMOTIONS, _emotion_view  # noqa: E402
from govern_legacy_gallery_tags import (  # noqa: E402
    backup_database,
    database_snapshot,
    write_asset_manifest,
)


def load_reviews(paths: list[Path]) -> list[list[dict[str, Any]]]:
    reviews = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"review_not_array:{path}")
        reviews.append(payload)
    if len(reviews) < 3:
        raise ValueError("at_least_three_reviews_required")
    return reviews


def normalize_review(raw: dict[str, Any]) -> dict[str, Any]:
    asset_id = int(raw.get("id") or 0)
    asset_ref = str(raw.get("asset_ref") or "")
    emotions = raw.get("emotions")
    if not isinstance(emotions, list) or not 1 <= len(emotions) <= 2:
        raise ValueError(f"emotion_count:{asset_ref}")
    normalized = []
    primary_count = 0
    seen = set()
    for emotion in emotions:
        if not isinstance(emotion, dict):
            raise ValueError(f"emotion_shape:{asset_ref}")
        emotion_tag = str(emotion.get("emotion_tag") or "").strip().lower()
        if ":" not in emotion_tag and f"emotion:{emotion_tag}" in EMOTIONS:
            emotion_tag = f"emotion:{emotion_tag}"
        intensity = int(emotion.get("intensity") or 0)
        prominence = str(emotion.get("prominence") or "")
        if emotion_tag not in EMOTIONS or emotion_tag in seen:
            raise ValueError(f"emotion_tag:{asset_ref}:{emotion_tag}")
        if intensity not in {1, 2, 3}:
            raise ValueError(f"emotion_intensity:{asset_ref}:{intensity}")
        if prominence not in {"primary", "secondary"}:
            raise ValueError(f"emotion_prominence:{asset_ref}:{prominence}")
        seen.add(emotion_tag)
        primary_count += int(prominence == "primary")
        normalized.append(
            {
                "emotion_tag": emotion_tag,
                "intensity": intensity,
                "prominence": prominence,
            }
        )
    if primary_count != 1:
        raise ValueError(f"primary_count:{asset_ref}")
    return {
        "id": asset_id,
        "asset_ref": asset_ref,
        "emotions": normalized,
        "confidence": str(raw.get("confidence") or "low").lower(),
        "needs_manual_review": bool(raw.get("needs_manual_review", True)),
        "note": str(raw.get("note") or "")[:500],
    }


def validate_reviews(
    database: Path, reviews: list[list[dict[str, Any]]]
) -> list[dict[int, dict[str, Any]]]:
    with sqlite3.connect(database) as conn:
        assets = {
            int(asset_id): str(asset_ref)
            for asset_id, asset_ref in conn.execute("SELECT id, asset_ref FROM gallery_assets")
        }
    normalized_sets = []
    expected_ids = None
    for review in reviews:
        normalized = {}
        for raw in review:
            item = normalize_review(raw)
            if assets.get(item["id"]) != item["asset_ref"] or item["id"] in normalized:
                raise ValueError(f"asset_identity:{item['id']}:{item['asset_ref']}")
            normalized[item["id"]] = item
        if expected_ids is None:
            expected_ids = set(normalized)
        elif set(normalized) != expected_ids:
            raise ValueError("review_asset_sets_differ")
        normalized_sets.append(normalized)
    return normalized_sets


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def build_consensus(
    reviews: list[dict[int, dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted = []
    unresolved = []
    threshold = len(reviews) // 2 + 1
    for asset_id in sorted(reviews[0]):
        items = [review[asset_id] for review in reviews]
        primary_values = [
            next(emotion for emotion in item["emotions"] if emotion["prominence"] == "primary")
            for item in items
        ]
        primary_counts = Counter(value["emotion_tag"] for value in primary_values)
        primary_tag, primary_votes = primary_counts.most_common(1)[0]
        primary_intensities = [
            value["intensity"] for value in primary_values if value["emotion_tag"] == primary_tag
        ]
        reasons = []
        if primary_votes < threshold:
            reasons.append("no_primary_majority")
        if primary_votes < len(reviews) and primary_values[-1]["emotion_tag"] != primary_tag:
            reasons.append("deliberate_review_disagrees")
        if primary_intensities and max(primary_intensities) - min(primary_intensities) > 1:
            reasons.append("primary_intensity_spread")

        secondary_votes: Counter[str] = Counter()
        secondary_intensities: dict[str, list[int]] = {}
        for item in items:
            for emotion in item["emotions"]:
                if emotion["prominence"] != "secondary":
                    continue
                tag = emotion["emotion_tag"]
                secondary_votes[tag] += 1
                secondary_intensities.setdefault(tag, []).append(emotion["intensity"])
        secondary_tag = ""
        if secondary_votes:
            candidate, votes = secondary_votes.most_common(1)[0]
            if votes >= threshold and candidate != primary_tag:
                intensities = secondary_intensities[candidate]
                if max(intensities) - min(intensities) <= 1:
                    secondary_tag = candidate

        comparison = {
            "id": asset_id,
            "asset_ref": items[0]["asset_ref"],
            "primary_votes": dict(primary_counts),
            "secondary_votes": dict(secondary_votes),
            "review_emotions": [item["emotions"] for item in items],
            "reasons": reasons,
        }
        if reasons:
            unresolved.append(comparison)
            continue
        emotions = [
            {
                "emotion_tag": primary_tag,
                "intensity": _median(primary_intensities),
                "prominence": "primary",
                "source": "consensus-reviewed",
                "suggestion_confidence": primary_votes / len(reviews),
            }
        ]
        if secondary_tag:
            values = secondary_intensities[secondary_tag]
            emotions.append(
                {
                    "emotion_tag": secondary_tag,
                    "intensity": _median(values),
                    "prominence": "secondary",
                    "source": "consensus-reviewed",
                    "suggestion_confidence": secondary_votes[secondary_tag] / len(reviews),
                }
            )
        accepted.append(
            {
                "id": asset_id,
                "asset_ref": items[0]["asset_ref"],
                "emotions": emotions,
                "needs_manual_review": True,
                "comparison": comparison,
            }
        )
    return accepted, unresolved


def apply_consensus(database: Path, values: list[dict[str, Any]]) -> int:
    store = GalleryStore(str(database.parent))
    store.db_path = database
    now = int(time.time())
    changed = 0
    with store._connect() as conn:
        for item in values:
            row = conn.execute(
                "SELECT * FROM gallery_assets WHERE id=? AND asset_ref=?",
                (item["id"], item["asset_ref"]),
            ).fetchone()
            if not row:
                raise RuntimeError(f"asset_changed:{item['asset_ref']}")
            current = store._row_to_asset(row)
            tags = [
                tag
                for tag in current["tags"]
                if not tag.startswith(("emotion:", "intensity:"))
            ]
            if REVIEW_TAG not in tags:
                tags.append(REVIEW_TAG)
            for emotion in item["emotions"]:
                if emotion["emotion_tag"] not in tags:
                    tags.append(emotion["emotion_tag"])
            tags = store.project_emotion_intensity(tags, item["emotions"])
            if tags == current["tags"] and _emotion_view(current["emotions"]) == _emotion_view(item["emotions"]):
                continue
            updated_at = max(now, int(row["updated_at"]) + 1)
            conn.execute(
                "UPDATE gallery_assets SET tags=?, updated_at=? WHERE id=?",
                (json.dumps(tags, ensure_ascii=False), updated_at, item["id"]),
            )
            store.replace_asset_tags(conn, item["id"], tags)
            store.replace_asset_emotions(conn, item["id"], tags, item["emotions"])
            store.record_review_change(conn, current, tags)
            changed += 1
        store.refresh_search_index(conn)
    return changed


def create_backup(
    database: Path, backup_root: Path, inputs: list[Path], report: dict[str, Any]
) -> Path:
    directory = backup_root / f"gallery-consensus-review-{time.strftime('%Y%m%d-%H%M%S')}"
    backup = backup_database(database, directory)
    write_asset_manifest(database, directory / "asset-sha256.jsonl")
    for index, path in enumerate(inputs, 1):
        shutil.copy2(path, directory / f"review-{index}.json")
    (directory / "consensus.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if database_snapshot(backup)["integrity_check"] != "ok":
        raise RuntimeError("consensus_backup_invalid")
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply multi-review emotion consensus")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument(
        "--review",
        type=Path,
        action="append",
        required=True,
        help="Ordered from quickest to most deliberate; the final review breaks ties.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    database = args.database.resolve()
    inputs = [path.resolve() for path in args.review]
    reviews = validate_reviews(database, load_reviews(inputs))
    accepted, unresolved = build_consensus(reviews)
    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "reviewers": len(reviews),
        "reviewed_assets": len(reviews[0]),
        "consensus_assets": len(accepted),
        "unresolved_assets": len(unresolved),
        "accepted": accepted,
        "unresolved": unresolved,
        "changed": 0,
        "backup_dir": "",
        "before": database_snapshot(database),
    }
    if args.apply:
        if not args.backup_root:
            raise SystemExit("backup_root_required_for_apply")
        payload["backup_dir"] = str(
            create_backup(database, args.backup_root.resolve(), inputs, payload)
        )
        store = GalleryStore(str(database.parent))
        store.db_path = database
        store.initialize()
        payload["changed"] = apply_consensus(database, accepted)
    payload["after"] = database_snapshot(database)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
