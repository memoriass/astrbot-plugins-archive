from __future__ import annotations

import argparse
from collections import Counter
import hashlib
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

from astrbot_plugin_plana_gallery.assets.constants import (  # noqa: E402
    DEFAULT_TAGS,
    RESTRICTED_TAG,
    REVIEW_TAG,
    SAFE_TAG,
)
from astrbot_plugin_plana_gallery.assets.store import GalleryStore  # noqa: E402
from govern_legacy_gallery_tags import (  # noqa: E402
    backup_database,
    database_snapshot,
    write_asset_manifest,
)

SOURCE_MAP = {
    "beta-visual-classification": "visual-reviewed",
    "multi-effort-consensus": "consensus-reviewed",
    "legacy-governance": "legacy-normalized",
}
EMOTION_TAGS = {tag for tag, *_ in DEFAULT_TAGS if tag.startswith("emotion:")}
CONTEXT_TAGS = {
    tag for tag, *_ in DEFAULT_TAGS
    if tag.startswith(("tone:", "scene:"))
}


def load_assignments(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("assignments_not_array")
    return [item for item in payload if isinstance(item, dict)]


def validate_assignments(
    database: Path, values: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    with sqlite3.connect(database) as conn:
        assets = {
            int(row[0]): str(row[1])
            for row in conn.execute("SELECT id, asset_ref FROM gallery_assets")
        }
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in values:
        asset_id = int(raw.get("id") or 0)
        asset_ref = str(raw.get("asset_ref") or "").strip()
        if asset_id in seen or assets.get(asset_id) != asset_ref:
            raise ValueError(f"assignment_identity:{asset_id}:{asset_ref}")
        seen.add(asset_id)
        emotions = _normalize_emotions(raw.get("emotions"), asset_ref)
        add_tags = _normalize_context_tags(raw.get("add_tags"), asset_ref)
        if emotions is None and not add_tags:
            raise ValueError(f"assignment_empty:{asset_ref}")
        result.append({
            "id": asset_id,
            "asset_ref": asset_ref,
            "emotions": emotions,
            "add_tags": add_tags,
            "reason": str(raw.get("reason") or "manual release review")[:500],
        })
    return sorted(result, key=lambda item: int(item["id"]))


def _normalize_emotions(
    values: Any, asset_ref: str
) -> list[dict[str, Any]] | None:
    if values is None:
        return None
    if not isinstance(values, list) or not 1 <= len(values) <= 2:
        raise ValueError(f"assignment_emotion_count:{asset_ref}")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_count = 0
    for index, raw in enumerate(values):
        if not isinstance(raw, dict):
            raise ValueError(f"assignment_emotion_shape:{asset_ref}")
        tag = str(raw.get("emotion_tag") or raw.get("tag") or "").strip().lower()
        if tag not in EMOTION_TAGS or tag in seen:
            raise ValueError(f"assignment_emotion_tag:{asset_ref}:{tag}")
        seen.add(tag)
        intensity = int(raw.get("intensity") or 0)
        if intensity not in {1, 2, 3}:
            raise ValueError(f"assignment_intensity:{asset_ref}:{intensity}")
        prominence = str(
            raw.get("prominence") or ("primary" if index == 0 else "secondary")
        )
        if prominence not in {"primary", "secondary"}:
            raise ValueError(f"assignment_prominence:{asset_ref}:{prominence}")
        primary_count += int(prominence == "primary")
        confidence = raw.get("suggestion_confidence")
        if confidence is not None:
            confidence = max(0.0, min(float(confidence), 1.0))
        result.append({
            "emotion_tag": tag,
            "intensity": intensity,
            "prominence": prominence,
            "source": "release-reviewed",
            "suggestion_confidence": confidence,
        })
    if primary_count != 1:
        raise ValueError(f"assignment_primary_count:{asset_ref}:{primary_count}")
    return result


def _normalize_context_tags(values: Any, asset_ref: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"assignment_context_shape:{asset_ref}")
    result: list[str] = []
    for value in values[:20]:
        tag = str(value or "").strip().lower()
        if tag not in CONTEXT_TAGS:
            raise ValueError(f"assignment_context_tag:{asset_ref}:{tag}")
        if tag not in result:
            result.append(tag)
    return result


def release_snapshot(database: Path) -> dict[str, Any]:
    base = database_snapshot(database)
    with sqlite3.connect(database) as conn:
        source_counts = dict(conn.execute(
            "SELECT source, COUNT(*) FROM gallery_asset_emotions GROUP BY source"
        ).fetchall())
        emotion_counts = dict(conn.execute(
            "SELECT emotion_tag, COUNT(*) FROM gallery_asset_emotions GROUP BY emotion_tag"
        ).fetchall())
        pending_safe = int(conn.execute(
            """SELECT COUNT(DISTINCT review.asset_id)
               FROM gallery_asset_tags review
               JOIN gallery_asset_tags safe ON safe.asset_id=review.asset_id
               WHERE review.tag=? AND safe.tag=?""",
            (REVIEW_TAG, SAFE_TAG),
        ).fetchone()[0])
    return {
        **base,
        "emotion_sources": source_counts,
        "emotion_counts": emotion_counts,
        "pending_safe_assets": pending_safe,
    }


def apply_release_data(
    database: Path,
    assignments: list[dict[str, Any]],
    asset_root: Path | None = None,
) -> dict[str, Any]:
    store = GalleryStore(str(database.parent))
    store.db_path = database
    source_updates: dict[str, int] = {}
    assigned = 0
    normalized_pending = 0
    repaired_paths = 0
    changed_assets: set[int] = set()
    assignment_map = {int(item["id"]): item for item in assignments}
    with store._connect() as conn:
        for old_source, new_source in SOURCE_MAP.items():
            cursor = conn.execute(
                "UPDATE gallery_asset_emotions SET source=? WHERE source=?",
                (new_source, old_source),
            )
            source_updates[old_source] = max(int(cursor.rowcount), 0)
        rows = conn.execute("SELECT * FROM gallery_assets ORDER BY id").fetchall()
        for row in rows:
            current = store._row_to_asset(row)
            current["emotions"] = store.emotions_for_asset(int(row["id"]), conn)
            file_path = str(row["file_path"])
            if asset_root is not None:
                repaired = _resolved_asset_path(asset_root, str(row["sha256"]), file_path)
                if repaired != file_path:
                    file_path = repaired
                    repaired_paths += 1
            tags = list(current["tags"])
            assignment = assignment_map.get(int(row["id"]))
            if REVIEW_TAG in tags and SAFE_TAG in tags:
                tags = [tag for tag in tags if tag != SAFE_TAG]
                normalized_pending += 1
            emotions = current.get("emotions", [])
            if assignment is not None:
                if REVIEW_TAG in tags or RESTRICTED_TAG in tags:
                    raise RuntimeError(f"assignment_not_approved:{assignment['asset_ref']}")
                if assignment["emotions"] is not None:
                    emotions = assignment["emotions"]
                    tags = [
                        tag for tag in tags
                        if not tag.startswith(("emotion:", "intensity:"))
                    ]
                    tags.extend(item["emotion_tag"] for item in emotions)
                    tags = store.project_emotion_intensity(tags, emotions)
                for tag in assignment["add_tags"]:
                    if tag not in tags:
                        tags.append(tag)
            current_view = _emotion_view(current.get("emotions", []))
            next_view = _emotion_view(emotions)
            if (
                tags == current["tags"]
                and current_view == next_view
                and file_path == str(row["file_path"])
            ):
                continue
            updated_at = max(store._now(), int(row["updated_at"]) + 1)
            conn.execute(
                "UPDATE gallery_assets SET file_path=?, tags=?, updated_at=? WHERE id=?",
                (
                    file_path,
                    json.dumps(tags, ensure_ascii=False),
                    updated_at,
                    int(row["id"]),
                ),
            )
            store.replace_asset_tags(conn, int(row["id"]), tags)
            store.replace_asset_emotions(conn, int(row["id"]), tags, emotions)
            store.record_review_change(conn, current, tags)
            changed_assets.add(int(row["id"]))
            assigned += int(assignment is not None)
        if changed_assets:
            store.refresh_search_index(conn)
    return {
        "source_updates": source_updates,
        "assigned_assets": assigned,
        "normalized_pending_assets": normalized_pending,
        "repaired_paths": repaired_paths,
        "changed_assets": len(changed_assets),
    }


def _resolved_asset_path(asset_root: Path, sha256: str, current_path: str) -> str:
    current = Path(current_path)
    if current.is_file() and _sha256(current) == sha256:
        return str(current.resolve())
    named = asset_root / current.name
    candidates = [named] if named.is_file() else sorted(asset_root.glob(f"{sha256}.*"))
    matches = [path for path in candidates if path.is_file() and _sha256(path) == sha256]
    if len(matches) != 1:
        raise RuntimeError(f"asset_path_unresolved:{sha256}:{len(matches)}")
    return str(matches[0].resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _emotion_view(values: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (
            str(value["emotion_tag"]),
            int(value["intensity"]),
            str(value["prominence"]),
            str(value.get("source") or ""),
        )
        for value in values
    )


def create_backup_bundle(
    database: Path,
    backup_root: Path,
    assignments_path: Path | None,
    before: dict[str, Any],
) -> Path:
    directory = backup_root / f"gallery-release-finalization-{time.strftime('%Y%m%d-%H%M%S')}"
    backup = backup_database(database, directory)
    manifest = write_asset_manifest(database, directory / "asset-sha256.jsonl")
    if assignments_path is not None:
        shutil.copy2(assignments_path, directory / "emotion-assignments.json")
    backup_state = release_snapshot(backup)
    (directory / "backup-summary.json").write_text(
        json.dumps(
            {"source": before, "backup": backup_state, "manifest": manifest},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if (
        before["assets"] != backup_state["assets"]
        or before["tag_relations"] != backup_state["tag_relations"]
        or backup_state["integrity_check"] != "ok"
    ):
        raise RuntimeError("release_backup_invalid")
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize Gallery provenance and curated emotion profiles"
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"database_not_found={database}")
    assignments_path = args.assignments.resolve() if args.assignments else None
    asset_root = args.asset_root.resolve() if args.asset_root else None
    if asset_root is not None and not asset_root.is_dir():
        raise SystemExit(f"asset_root_not_found={asset_root}")
    assignments = validate_assignments(
        database, load_assignments(assignments_path)
    )
    before = release_snapshot(database)
    backup_dir = None
    changes = {
        "source_updates": Counter(before["emotion_sources"]),
        "assigned_assets": len(assignments),
        "normalized_pending_assets": before["pending_safe_assets"],
        "repaired_paths": 0,
        "changed_assets": 0,
    }
    if args.apply:
        if not args.backup_root:
            raise SystemExit("backup_root_required_for_apply")
        backup_dir = create_backup_bundle(
            database, args.backup_root.resolve(), assignments_path, before
        )
        store = GalleryStore(str(database.parent))
        store.db_path = database
        store.initialize()
        changes = apply_release_data(database, assignments, asset_root)
    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry-run",
        "backup_dir": str(backup_dir) if backup_dir else "",
        "assignments": len(assignments),
        "changes": changes,
        "before": before,
        "after": release_snapshot(database),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=dict)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
