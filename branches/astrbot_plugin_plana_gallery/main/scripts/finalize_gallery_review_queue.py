from __future__ import annotations

import argparse
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


def load_classification(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("classification_not_array")
    return [item for item in payload if isinstance(item, dict)]


def load_consensus(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("consensus_not_object")
    return payload


def review_plan(
    database: Path,
    classification: list[dict[str, Any]],
    consensus: dict[str, Any],
) -> dict[str, Any]:
    with sqlite3.connect(database) as conn:
        assets = {
            int(asset_id): str(asset_ref)
            for asset_id, asset_ref in conn.execute("SELECT id, asset_ref FROM gallery_assets")
        }
        current_review = {
            int(asset_id)
            for (asset_id,) in conn.execute(
                "SELECT asset_id FROM gallery_asset_tags WHERE tag=?", (REVIEW_TAG,)
            )
        }
    classified: dict[int, dict[str, Any]] = {}
    for item in classification:
        asset_id = int(item.get("id") or 0)
        asset_ref = str(item.get("asset_ref") or "")
        if assets.get(asset_id) != asset_ref or asset_id in classified:
            raise ValueError(f"classification_identity:{asset_id}:{asset_ref}")
        classified[asset_id] = item
    if set(classified) != set(assets):
        raise ValueError(f"classification_coverage:{len(classified)}!={len(assets)}")

    manual = {
        asset_id
        for asset_id, item in classified.items()
        if bool(item.get("needs_manual_review"))
    }
    accepted = _consensus_ids(consensus.get("accepted"), assets, "accepted")
    unresolved = _consensus_ids(consensus.get("unresolved"), assets, "unresolved")
    if accepted & unresolved:
        raise ValueError("consensus_sets_overlap")
    if accepted | unresolved != manual:
        raise ValueError("consensus_does_not_cover_manual_set")
    keep_review = unresolved
    remove_review = current_review - keep_review
    add_review = keep_review - current_review
    return {
        "assets": len(assets),
        "classified": len(classified),
        "manual_before_consensus": len(manual),
        "consensus_accepted": len(accepted),
        "keep_review_ids": sorted(keep_review),
        "remove_review_ids": sorted(remove_review),
        "add_review_ids": sorted(add_review),
        "current_review": len(current_review),
        "final_review": len(keep_review),
    }


def _consensus_ids(
    values: Any, assets: dict[int, str], label: str
) -> set[int]:
    if not isinstance(values, list):
        raise ValueError(f"consensus_{label}_not_array")
    result = set()
    for item in values:
        if not isinstance(item, dict):
            raise ValueError(f"consensus_{label}_shape")
        asset_id = int(item.get("id") or 0)
        asset_ref = str(item.get("asset_ref") or "")
        if assets.get(asset_id) != asset_ref or asset_id in result:
            raise ValueError(f"consensus_{label}_identity:{asset_id}:{asset_ref}")
        result.add(asset_id)
    return result


def apply_plan(database: Path, plan: dict[str, Any]) -> dict[str, int]:
    store = GalleryStore(str(database.parent))
    store.db_path = database
    keep_review = set(plan["keep_review_ids"])
    changed = 0
    approved = 0
    queued = 0
    now = int(time.time())
    with store._connect() as conn:
        rows = conn.execute("SELECT * FROM gallery_assets ORDER BY id").fetchall()
        if len(rows) != int(plan["assets"]):
            raise RuntimeError("assets_changed_since_preview")
        for row in rows:
            asset_id = int(row["id"])
            current = store._row_to_asset(row)
            tags = list(current["tags"])
            should_review = asset_id in keep_review
            has_review = REVIEW_TAG in tags
            if should_review == has_review:
                continue
            if should_review:
                tags.append(REVIEW_TAG)
                queued += 1
            else:
                tags = [tag for tag in tags if tag != REVIEW_TAG]
                approved += 1
            updated_at = max(now, int(row["updated_at"]) + 1)
            conn.execute(
                "UPDATE gallery_assets SET tags=?, updated_at=? WHERE id=?",
                (json.dumps(tags, ensure_ascii=False), updated_at, asset_id),
            )
            store.replace_asset_tags(conn, asset_id, tags)
            store.record_review_change(conn, current, tags)
            store.refresh_search_index(conn, asset_id)
            changed += 1
    return {"changed": changed, "approved": approved, "queued": queued}


def create_backup(
    database: Path,
    backup_root: Path,
    classification: Path,
    consensus: Path,
    plan: dict[str, Any],
) -> Path:
    directory = backup_root / f"gallery-review-queue-finalize-{time.strftime('%Y%m%d-%H%M%S')}"
    backup = backup_database(database, directory)
    write_asset_manifest(database, directory / "asset-sha256.jsonl")
    shutil.copy2(classification, directory / "classification.json")
    shutil.copy2(consensus, directory / "consensus.json")
    (directory / "review-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if database_snapshot(backup)["integrity_check"] != "ok":
        raise RuntimeError("review_queue_backup_invalid")
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize Gallery human review queue")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--consensus", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    database = args.database.resolve()
    classification_path = args.classification.resolve()
    consensus_path = args.consensus.resolve()
    plan = review_plan(
        database,
        load_classification(classification_path),
        load_consensus(consensus_path),
    )
    result = {"changed": 0, "approved": 0, "queued": 0}
    backup_dir = ""
    if args.apply:
        if not args.backup_root:
            raise SystemExit("backup_root_required_for_apply")
        backup_dir = str(
            create_backup(
                database,
                args.backup_root.resolve(),
                classification_path,
                consensus_path,
                plan,
            )
        )
        store = GalleryStore(str(database.parent))
        store.db_path = database
        store.initialize()
        result = apply_plan(database, plan)
    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "backup_dir": backup_dir,
        "plan": plan,
        **result,
        "database": database_snapshot(database),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
