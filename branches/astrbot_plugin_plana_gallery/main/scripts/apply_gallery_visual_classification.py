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
from govern_legacy_gallery_tags import (  # noqa: E402
    backup_database,
    database_snapshot,
    write_asset_manifest,
)

EMOTIONS = {
    "emotion:happy", "emotion:excited", "emotion:amused", "emotion:affection",
    "emotion:grateful", "emotion:proud", "emotion:relieved", "emotion:surprised",
    "emotion:hopeful", "emotion:playful", "emotion:calm", "emotion:confused",
    "emotion:curious", "emotion:speechless", "emotion:helpless", "emotion:shy",
    "emotion:embarrassed", "emotion:sad", "emotion:wronged",
    "emotion:disappointed", "emotion:frustrated", "emotion:guilty",
    "emotion:angry", "emotion:annoyed", "emotion:afraid", "emotion:nervous",
    "emotion:panicked", "emotion:disgusted", "emotion:tired", "emotion:bored",
    "emotion:comfort",
}
CONFIDENCE_VALUE = {"high": 0.9, "medium": 0.7, "low": 0.45}


def load_classifications(paths: list[Path]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"classification_not_array:{path}")
        values.extend(item for item in payload if isinstance(item, dict))
    return values


def validate(
    database: Path, values: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        assets = {
            int(row["id"]): str(row["asset_ref"])
            for row in conn.execute("SELECT id, asset_ref FROM gallery_assets")
        }
    if len(values) != len(assets):
        raise ValueError(f"classification_count:{len(values)}!={len(assets)}")
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for raw in values:
        asset_id = int(raw.get("id") or 0)
        asset_ref = str(raw.get("asset_ref") or "")
        if asset_id in seen or assets.get(asset_id) != asset_ref:
            raise ValueError(f"classification_identity:{asset_id}:{asset_ref}")
        seen.add(asset_id)
        confidence = str(raw.get("confidence") or "low").lower()
        if confidence not in CONFIDENCE_VALUE:
            raise ValueError(f"classification_confidence:{asset_ref}")
        emotions = _normalize_emotions(raw.get("emotions"), confidence, asset_ref)
        add_tags: list[str] = []
        normalized.append({
            "id": asset_id, "asset_ref": asset_ref, "emotions": emotions,
            "add_tags": add_tags, "confidence": confidence,
            "needs_manual_review": bool(raw.get("needs_manual_review")) or confidence == "low",
            "note": str(raw.get("note") or "")[:500],
        })
    if seen != set(assets):
        raise ValueError("classification_missing_assets")
    return sorted(normalized, key=lambda item: int(item["id"]))


def _normalize_emotions(
    raw_values: Any, confidence: str, asset_ref: str
) -> list[dict[str, Any]]:
    if not isinstance(raw_values, list) or not 1 <= len(raw_values) <= 2:
        raise ValueError(f"classification_emotion_count:{asset_ref}")
    result = []
    seen: set[str] = set()
    primary_count = 0
    for index, raw in enumerate(raw_values):
        if not isinstance(raw, dict):
            raise ValueError(f"classification_emotion_shape:{asset_ref}")
        tag = str(raw.get("emotion_tag") or "").strip().lower()
        if tag not in EMOTIONS or tag in seen:
            raise ValueError(f"classification_emotion_tag:{asset_ref}:{tag}")
        seen.add(tag)
        intensity = int(raw.get("intensity") or 0)
        if intensity not in {1, 2, 3}:
            raise ValueError(f"classification_intensity:{asset_ref}:{intensity}")
        prominence = str(raw.get("prominence") or ("primary" if index == 0 else "secondary"))
        if prominence not in {"primary", "secondary"}:
            raise ValueError(f"classification_prominence:{asset_ref}")
        primary_count += int(prominence == "primary")
        result.append({
            "emotion_tag": tag, "intensity": intensity, "prominence": prominence,
            "source": "visual-reviewed",
            "suggestion_confidence": CONFIDENCE_VALUE[confidence],
        })
    if primary_count != 1:
        raise ValueError(f"classification_primary_count:{asset_ref}:{primary_count}")
    return result


def summarize(values: list[dict[str, Any]]) -> dict[str, Any]:
    emotions = Counter()
    intensities = Counter()
    confidences = Counter()
    tags = Counter()
    for item in values:
        confidences[item["confidence"]] += 1
        for emotion in item["emotions"]:
            emotions[emotion["emotion_tag"]] += 1
            intensities[str(emotion["intensity"])] += 1
        tags.update(item["add_tags"])
    return {
        "assets": len(values), "manual_review": sum(
            int(item["needs_manual_review"]) for item in values
        ),
        "confidence": dict(confidences), "emotions": dict(emotions.most_common()),
        "intensities": dict(intensities), "controlled_tags": dict(tags.most_common()),
    }


def apply(database: Path, values: list[dict[str, Any]]) -> int:
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
                tag for tag in current["tags"]
                if not tag.startswith(("emotion:", "intensity:"))
            ]
            if item["needs_manual_review"] and REVIEW_TAG not in tags:
                tags.append(REVIEW_TAG)
            for tag in [
                *(emotion["emotion_tag"] for emotion in item["emotions"]),
                *item["add_tags"],
            ]:
                if tag not in tags:
                    tags.append(tag)
            tags = store.project_emotion_intensity(tags, item["emotions"])
            if tags != current["tags"] or _emotion_view(current["emotions"]) != _emotion_view(item["emotions"]):
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


def _emotion_view(values: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (value["emotion_tag"], int(value["intensity"]), value["prominence"])
        for value in values
    )


def create_backup(
    database: Path, backup_root: Path, values: list[dict[str, Any]], inputs: list[Path]
) -> Path:
    directory = backup_root / f"gallery-visual-classification-{time.strftime('%Y%m%d-%H%M%S')}"
    backup = backup_database(database, directory)
    write_asset_manifest(database, directory / "asset-sha256.jsonl")
    (directory / "classification.json").write_text(
        json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for path in inputs:
        shutil.copy2(path, directory / f"input-{path.parent.name}.json")
    source_state = database_snapshot(database)
    backup_state = database_snapshot(backup)
    (directory / "backup-summary.json").write_text(
        json.dumps({"source": source_state, "backup": backup_state}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if source_state["assets"] != backup_state["assets"] or backup_state["integrity_check"] != "ok":
        raise RuntimeError("classification_backup_invalid")
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply controlled visual classification")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    database = args.database.resolve()
    inputs = [path.resolve() for path in args.input]
    values = validate(database, load_classifications(inputs))
    before = database_snapshot(database)
    summary = summarize(values)
    backup_dir = None
    changed = 0
    if args.apply:
        if not args.backup_root:
            raise SystemExit("backup_root_required_for_apply")
        backup_dir = create_backup(database, args.backup_root.resolve(), values, inputs)
        store = GalleryStore(str(database.parent))
        store.db_path = database
        store.initialize()
        changed = apply(database, values)
    payload = {
        "ok": True, "mode": "apply" if args.apply else "dry-run",
        "backup_dir": str(backup_dir) if backup_dir else "", "changed": changed,
        "before": before, "after": database_snapshot(database), "summary": summary,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
