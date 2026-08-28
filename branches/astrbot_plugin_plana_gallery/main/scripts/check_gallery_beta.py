from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile

from gallery_beta_emotions import check_emotion_profiles
from apply_gallery_consensus_review import build_consensus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from check_core_loopback import check_core_loopback  # noqa: E402
MAX_LINES = 500

EXPECTED_FILES = (
    "README.md", "ARCHITECTURE.md", "metadata.yaml", "_conf_schema.json",
    "assets/store.py", "assets/schema.py", "assets/chat_search.py", "assets/query.py",
    "assets/constants.py", "assets/derivatives.py", "assets/transactions.py",
    "assets/serialization.py", "assets/collection.py", "assets/governance.py",
    "assets/tag_governance.py",
    "plugin/runtime.py", "plugin/chat_service.py", "plugin/chat_server.py",
    "plugin/chat_api.py", "plugin/management_api.py",
    "plugin/config.py", "plugin/ingest.py", "plugin/tagging.py",
    "commands/gallery.py", "commands/collection.py",
    "scripts/run_gallery_web_preview.py",
    "scripts/govern_legacy_gallery_tags.py",
    "scripts/apply_gallery_visual_classification.py",
    "scripts/apply_gallery_consensus_review.py",
    "scripts/finalize_gallery_review_queue.py",
    "scripts/finalize_gallery_release_data.py",
    "scripts/check_core_loopback.py",
    "web/page.py", "web/dist/index.html", "web/frontend/package.json",
    "web/frontend/src/App.vue", "web/frontend/src/utils/emotionGuides.ts", "logo.png",
)
REQUIRED_ENDPOINTS = (
    "/plana_gallery/dashboard", "/plana_gallery/api/status",
    "/plana_gallery/api/assets", "/plana_gallery/api/assets/get",
    "/plana_gallery/api/chat/candidates", "/plana_gallery/api/chat/feedback",
    "/plana_gallery/api/chat/resolve", "/plana_gallery/api/tags",
    "/plana_gallery/api/assets/import", "/plana_gallery/api/assets/upload",
    "/plana_gallery/api/assets/import-urls", "/plana_gallery/api/tagging/batch",
    "/plana_gallery/api/assets/thumbnail/<asset_id>",
    "/plana_gallery/api/assets/thumbnail/<asset_id>/rebuild",
    "/plana_gallery/api/review/commit",
    "/plana_gallery/api/diagnostics/query",
    "/plana_gallery/api/jobs",
)
REMOTE_TERMS = ("lsky", "chevereto", "lychee", "remote_provider", "auto_remote_upload")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    check_files_and_sizes()
    check_metadata_and_schema()
    check_runtime_contract()
    check_web_shell()
    check_local_lifecycle()
    check_consensus_review()
    asyncio.run(check_core_loopback())
    check_logo()
    print("gallery_beta_check=ok")


def check_files_and_sizes() -> None:
    missing = [name for name in EXPECTED_FILES if not (ROOT / name).is_file()]
    require(not missing, f"missing_files={missing}")
    offenders = []
    for path in ROOT.rglob("*"):
        if (
            ".git" in path.parts
            or "__pycache__" in path.parts
            or "node_modules" in path.parts
            or path.name == "package-lock.json"
            or not path.is_file()
        ):
            continue
        if path.suffix not in {".py", ".md", ".json", ".yaml", ".yml"}:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            offenders.append(f"{path.relative_to(ROOT)}:{len(lines)}")
    require(not offenders, f"line_limit_exceeded={offenders}")


def check_metadata_and_schema() -> None:
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    require("Plana Gallery" in metadata and "gallery" in metadata, "metadata_invalid")
    require("-beta" not in metadata.lower(), "metadata_still_beta")
    entrypoint = (ROOT / "main.py").read_text(encoding="utf-8")
    require("@register(" in entrypoint, "astrbot_registration_missing")
    require('"astrbot_plugin_plana_gallery"' in entrypoint, "registration_name_missing")
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    for key in (
        "enabled", "api_token", "core_service_http_enabled",
        "core_service_port", "core_service_key", "max_import_bytes", "allow_original_path",
        "enable_commands", "allow_chat_image_import", "tagging_ai_enabled",
        "enable_silent_chat_image_collection", "silent_collection_scope_allowlist",
        "silent_collection_daily_limit_per_scope", "silent_collection_global_daily_limit",
        "silent_collection_max_images_per_message", "silent_collection_max_bytes",
        "silent_collection_max_pixels", "silent_collection_max_gif_frames",
        "tagging_ai_provider", "tagging_confidence_threshold",
    ):
        require(key in schema, f"schema_missing={key}")
    require(not any(term in schema for term in REMOTE_TERMS), "remote_schema_not_removed")


def check_runtime_contract() -> None:
    runtime = (ROOT / "plugin" / "runtime.py").read_text(encoding="utf-8")
    missing = [endpoint for endpoint in REQUIRED_ENDPOINTS if endpoint not in runtime]
    require(not missing, f"endpoint_missing={missing}")
    require("GallerySyncService" not in runtime, "remote_runtime_still_loaded")
    require("secrets.compare_digest" in runtime, "auth_compare_missing")
    chat_server = (ROOT / "plugin" / "chat_server.py").read_text(encoding="utf-8")
    require('"127.0.0.1"' in chat_server, "loopback_bind_missing")
    require("X-Plana-Core-Key" in chat_server, "core_service_key_missing")
    schema = (ROOT / "assets" / "schema.py").read_text(encoding="utf-8")
    schema += (ROOT / "assets" / "emotions.py").read_text(encoding="utf-8")
    schema += (ROOT / "assets" / "governance.py").read_text(encoding="utf-8")
    search = (ROOT / "assets" / "chat_search.py").read_text(encoding="utf-8")
    for snippet in (
        "gallery_schema_meta", "gallery_tag_definitions", "gallery_tag_aliases",
        "gallery_candidate_events", "gallery_assets_fts", "gallery_asset_emotions",
        "SCHEMA_VERSION = 5", "gallery_tag_governance_audit",
    ):
        require(snippet in schema, f"schema_contract_missing={snippet}")
    for snippet in ("reviewed", "safety", "score_breakdown", "recent_penalty"):
        require(snippet in search, f"search_contract_missing={snippet}")


def check_web_shell() -> None:
    from astrbot_plugin_plana_gallery.web.page import gallery_html

    text = gallery_html()
    require("id=\"app\"" in text, "vue_mount_missing")
    require("__PLANA_GALLERY_API_BASE__" not in text, "api_base_not_injected")
    require("Plana Gallery" in text, "web_title_missing")
    require("强度标注准则" in text, "emotion_intensity_rubric_missing")
    require("无法确定情绪或语境的素材会进入待审核" in text, "review_routing_guidance_missing")
    require("localStorage" not in text, "page_persistent_token_storage")
    for term in ("小维", "fixture", "情绪素材覆盖", "尚无明确素材标签"):
        require(term not in text, f"production_test_content={term}")
    require(not any(term in text.lower() for term in REMOTE_TERMS), "remote_web_not_removed")


def check_local_lifecycle() -> None:
    from astrbot_plugin_plana_gallery.assets.store import GalleryStore

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR42mP8z8AARAwMjDAGDAAAAP//AwAHEgIDFQq6WQAAAABJRU5ErkJggg=="
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = GalleryStore(tmp)
        store.initialize()
        taxonomy = store.tag_taxonomy()
        definitions = {item["tag"]: item for item in taxonomy["definitions"]}
        expected_emotions = {
            "emotion:happy", "emotion:excited", "emotion:amused",
            "emotion:affection", "emotion:grateful", "emotion:proud",
            "emotion:relieved", "emotion:surprised", "emotion:confused",
            "emotion:speechless", "emotion:shy", "emotion:embarrassed",
            "emotion:sad", "emotion:disappointed", "emotion:angry",
            "emotion:annoyed", "emotion:afraid", "emotion:nervous",
            "emotion:disgusted", "emotion:tired", "emotion:bored",
        }
        require(expected_emotions <= definitions.keys(), "emotion_taxonomy_incomplete")
        require(
            all(definitions[tag]["description"] for tag in expected_emotions),
            "emotion_descriptions_missing",
        )
        require("governance" in taxonomy, "governance_status_missing")
        require(
            store.canonicalize_tags(["紧张", "尴尬", "松口气"])
            == ["emotion:nervous", "emotion:embarrassed", "emotion:relieved"],
            "emotion_aliases_not_canonicalized",
        )
        require(store.canonicalize_tags(["happy"]) == ["emotion:happy"],
                "legacy_direct_tag_not_normalized")
        require(store.canonicalize_tags(["sigh"]) == ["sigh", "needs-review"],
                "ambiguous_legacy_tag_not_queued")
        require(store.canonicalize_tags(["sigh", "emotion:helpless"]) == ["emotion:helpless"],
                "classified_legacy_tag_not_removed_on_write")
        require(store.canonicalize_tags(["color"]) == ["color"],
                "content_tag_not_preserved")
        imported = store.import_bytes(
            png, filename="happy.png", caption="开心赞同", tags=["开心", "tone:agree"]
        )
        require(imported["ok"], f"fixture_import_failed={imported}")
        asset = imported["asset"]
        digest = asset["sha256"]
        require(store.chat_collection_hash_status(digest)["status"] == "existing",
                "collection_hash_lookup_failed")
        store.record_chat_collection(
            scope_hash="scope", sender_hash="sender", message_hash="message",
            asset_ref=asset["asset_ref"], outcome="collected",
        )
        require(store.chat_collection_counts(scope_hash="scope", since=0) == {"scope": 1, "global": 1},
                "collection_quota_count_failed")
        require(store.chat_collection_status()["collected"] == 1,
                "collection_status_failed")
        require("emotion:happy" in asset["tags"], "alias_not_canonicalized")
        require("safety:safe" in asset["tags"], "reviewed_safety_missing")
        candidates = store.chat_candidates(
            request_id="request:1", query="开心", facets=["开心"],
            exclude_asset_refs=[], limit=6,
        )
        require(candidates and candidates[0]["asset_ref"] == asset["asset_ref"], candidates)
        selected = store.record_chat_feedback(
            event_id="event:selected", request_id="request:1",
            asset_ref=asset["asset_ref"], event="selected",
        )
        replay = store.record_chat_feedback(
            event_id="event:selected", request_id="request:1",
            asset_ref=asset["asset_ref"], event="selected",
        )
        delivered = store.record_chat_feedback(
            event_id="event:delivered", request_id="request:1",
            asset_ref=asset["asset_ref"], event="delivered",
        )
        require(selected["ok"] and replay["idempotent_replay"] and delivered["ok"], "feedback_failed")
        require(store.resolve_chat_asset(asset["asset_ref"])["ok"], "asset_resolve_failed")
        pending = store.import_bytes(png + b"-pending", filename="pending.png")
        require(pending["ok"] and "needs-review" in pending["asset"]["tags"], "pending_import_failed")
        tagged = store.update_asset(pending["asset"]["id"], tags=["emotion:happy"])
        require("needs-review" in tagged["asset"]["tags"], "tag_edit_auto_approved")
        approved = store.update_asset(
            pending["asset"]["id"], tags=tagged["asset"]["tags"], approve=True
        )
        require("needs-review" not in approved["asset"]["tags"], "explicit_approval_failed")
        require("safety:safe" in approved["asset"]["tags"], "approval_safety_missing")
        pending_two = store.import_bytes(png + b"-pending-two", filename="pending-two.png")
        require(pending_two["ok"], "second_pending_import_failed")
        atomic = store.review_commit(
            [
                {
                    "id": approved["asset"]["id"],
                    "expected_updated_at": approved["asset"]["updated_at"],
                    "add_tags": ["tone:agree"],
                },
                {
                    "id": pending_two["asset"]["id"],
                    "expected_updated_at": pending_two["asset"]["updated_at"] + 1,
                    "add_tags": ["emotion:happy"],
                },
            ],
            approve=True,
        )
        require(not atomic["ok"] and atomic["error"] == "version_conflict", "review_conflict_missing")
        unchanged = store.get_asset(approved["asset"]["id"])
        require("tone:agree" not in unchanged["tags"], "review_transaction_not_rolled_back")
        page = store.list_assets_page(limit=1)
        require(len(page["assets"]) == 1, "cursor_page_failed")
        browsed = store.browse_assets(
            tags=["emotion:happy"], page=1, page_size=12, review="ready"
        )
        require(
            browsed["total"] == 2
            and browsed["page_count"] == 1
            and {row["asset_ref"] for row in browsed["assets"]}
            == {asset["asset_ref"], approved["asset"]["asset_ref"]},
            "browse_filter_failed",
        )
        pending_page = store.browse_assets(review="pending", page=1, page_size=12)
        require(pending_page["total"] == 1, "browse_review_filter_failed")
        thumbnail, mime_type = store.ensure_thumbnail(asset["id"], 320)
        require(thumbnail.is_file() and mime_type == "image/webp", "thumbnail_failed")
        require(store.derivative_facts(asset["id"])["thumbnails"], "derivative_missing")
        Path(asset["file_path"]).write_bytes(png + b"-changed")
        stale = store.thumbnail_status(asset["id"], 320)
        require(stale["ok"] and not stale["ready"], "stale_thumbnail_not_queued")
        with store._connect() as conn:
            status = conn.execute(
                "SELECT status FROM gallery_asset_derivatives WHERE asset_id=? AND size=320",
                (asset["id"],),
            ).fetchone()
        require(status and status["status"] == "stale", "stale_thumbnail_not_marked")
        store.ensure_thumbnail(asset["id"], 320)
        with store._connect() as conn:
            conn.execute("DELETE FROM gallery_jobs")
            conn.execute(
                """INSERT INTO gallery_jobs
                   (dedupe_key, job_type, payload, status, available_at, created_at, updated_at)
                   VALUES ('unsupported:test', 'unsupported', '{}', 'pending', 0, 1, 1)"""
            )
        for _ in range(3):
            store.process_next_job()
            with store._connect() as conn:
                conn.execute("UPDATE gallery_jobs SET available_at=0 WHERE dedupe_key='unsupported:test'")
        failed_job = store.jobs_status()["jobs"][0]
        require(failed_job["status"] == "failed" and failed_job["attempts"] == 3, "job_retry_policy_failed")
        with store._connect() as conn:
            conn.execute(
                "UPDATE gallery_jobs SET status='running', started_at=0 WHERE id=(SELECT MIN(id) FROM gallery_jobs)"
            )
        store.initialize()
        jobs = store.jobs_status()
        require(not jobs["counts"].get("running"), "running_job_not_recovered")
        diagnostics = store.chat_diagnostics(
            request_id="diagnostics:1", query="开心", facets=["emotion:happy"],
            exclude_asset_refs=[asset["asset_ref"]], limit=6,
        )
        require(
            any(item["asset_ref"] == asset["asset_ref"] for item in diagnostics["exclusions"]),
            "diagnostics_exclusion_missing",
        )
        check_emotion_profiles(store, png, require)
        check_tag_governance(store, png)
        first_definition = store.save_tag_definition(
            tag="tone:agree", label="赞同", aliases=["same-meaning"]
        )
        require(first_definition["ok"], "tag_definition_save_failed")
        alias_conflict = store.save_tag_definition(
            tag="tone:teasing", label="调侃", aliases=["same-meaning"]
        )
        require(
            not alias_conflict["ok"]
            and alias_conflict["error"] == "alias_conflict"
            and alias_conflict["canonical_tag"] == "tone:agree",
            "tag_alias_conflict_not_blocked",
        )
        canonical_conflict = store.save_tag_definition(
            tag="tone:teasing", label="调侃", aliases=["emotion:happy"]
        )
        require(
            not canonical_conflict["ok"]
            and canonical_conflict["error"] == "alias_conflicts_with_canonical",
            "canonical_tag_used_as_alias",
        )
        deleted = store.delete_asset(asset["id"])
        require(
            deleted["ok"] and store.asset_tombstone(asset["asset_ref"])
            and not thumbnail.exists(),
            "tombstone_or_derivative_cleanup_failed",
        )
    check_legacy_database_upgrade()


def check_legacy_database_upgrade() -> None:
    from astrbot_plugin_plana_gallery.assets.store import GalleryStore

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        asset_dir = root / "assets"
        asset_dir.mkdir(parents=True)
        asset_path = asset_dir / "legacy.png"
        asset_path.write_bytes(b"\x89PNG\r\n\x1a\nlegacy")
        db_path = root / "gallery.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE gallery_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_ref TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    original_path TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    caption TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    source TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )"""
            )
            conn.execute(
                """INSERT INTO gallery_assets
                   (asset_ref, sha256, file_path, original_path, mime_type,
                    title, caption, tags, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "gallery:legacy", "legacy-sha", str(asset_path),
                    "C:/legacy/source.png", "image/png", "legacy-title",
                    "legacy-caption", '["sleep", "sigh"]',
                    "meme_manager_import", 1, 2,
                ),
            )
        conn.close()
        store = GalleryStore(tmp)
        store.initialize()
        asset = store.get_asset_by_ref("gallery:legacy")
        require(asset is not None, "legacy_asset_missing_after_upgrade")
        require(asset["tags"] == ["sleep", "sigh", "safety:safe"], "legacy_tags_changed")
        require(asset["title"] == "legacy-title", "legacy_title_changed")
        require(asset["caption"] == "legacy-caption", "legacy_caption_changed")
        require(asset["source"] == "meme_manager_import", "legacy_source_changed")
        require(asset["original_path"] == "C:/legacy/source.png", "legacy_path_changed")
        candidates = store.chat_candidates(
            request_id="legacy:1", query="sleep", facets=["sleep"],
            exclude_asset_refs=[], limit=3,
        )
        require(candidates and candidates[0]["asset_ref"] == "gallery:legacy", "legacy_candidate_missing")
        edited = store.update_asset(asset["id"], tags=["sleep", "sigh", "classic"])
        require(
            edited["asset"]["tags"] == ["sleep", "sigh", "classic", "needs-review"],
            "ambiguous_write_not_routed_to_review",
        )


def check_tag_governance(store, png: bytes) -> None:
    happy = store.import_bytes(png + b"-legacy-happy", filename="legacy-happy.png", tags=["happy"])
    sigh = store.import_bytes(png + b"-legacy-sigh", filename="legacy-sigh.png", tags=["sigh"])
    classified = store.import_bytes(
        png + b"-legacy-classified", filename="legacy-classified.png",
        tags=["sad", "emotion:wronged"],
    )
    kept = store.import_bytes(png + b"-legacy-color", filename="legacy-color.png", tags=["color"])
    require(happy["ok"] and sigh["ok"] and classified["ok"] and kept["ok"], "governance_fixture_import_failed")
    with store._connect() as conn:
        legacy_tags = {
            happy["asset"]["id"]: ["happy", "safety:safe"],
            sigh["asset"]["id"]: ["sigh", "safety:safe"],
            classified["asset"]["id"]: ["sad", "emotion:wronged", "safety:safe"],
        }
        for asset_id, tags in legacy_tags.items():
            conn.execute(
                "UPDATE gallery_assets SET tags=? WHERE id=?",
                (json.dumps(tags, ensure_ascii=False), asset_id),
            )
            store.replace_asset_tags(conn, asset_id, tags)
    dry_run = store.govern_legacy_tags(apply=False)
    require(dry_run["summary"]["matched_relations"] >= 3, "governance_dry_run_missing")
    first = store.govern_legacy_tags(apply=True, batch_id="beta-governance-1")
    require(first["ok"] and first["summary"]["new_audit_events"] >= 3, "governance_apply_failed")
    happy_after = store.get_asset(happy["asset"]["id"])
    sigh_after = store.get_asset(sigh["asset"]["id"])
    classified_after = store.get_asset(classified["asset"]["id"])
    kept_after = store.get_asset(kept["asset"]["id"])
    require("happy" not in happy_after["tags"] and "emotion:happy" in happy_after["tags"],
            "direct_normalization_failed")
    require(happy_after["emotions"][0]["intensity"] == 2, "legacy_intensity_not_defaulted")
    require("needs-review" in sigh_after["tags"], "ambiguous_tag_not_queued")
    require("safety:safe" not in sigh_after["tags"], "queued_asset_kept_safe_status")
    require("emotion:speechless" not in sigh_after["tags"], "ambiguous_tag_guessed")
    require("sad" not in classified_after["tags"] and "emotion:wronged" in classified_after["tags"],
            "classified_legacy_tag_not_removed")
    require("needs-review" not in classified_after["tags"], "classified_asset_requeued")
    require("color" in kept_after["tags"] and "needs-review" not in kept_after["tags"],
            "kept_tag_changed")
    second = store.govern_legacy_tags(apply=True, batch_id="beta-governance-2")
    require(second["summary"]["new_audit_events"] == 0, "governance_audit_not_idempotent")
    require(second["summary"]["changed_assets"] == 0, "governance_changes_not_idempotent")


def check_consensus_review() -> None:
    def item(primary: str, intensity: int) -> dict:
        return {
            1: {
                "id": 1,
                "asset_ref": "gallery:test",
                "emotions": [{
                    "emotion_tag": primary,
                    "intensity": intensity,
                    "prominence": "primary",
                }],
            }
        }

    accepted, unresolved = build_consensus([
        item("emotion:happy", 1),
        item("emotion:surprised", 2),
        item("emotion:happy", 2),
    ])
    require(len(accepted) == 1 and not unresolved, "consensus_majority_failed")
    require(accepted[0]["emotions"][0]["intensity"] == 2, "consensus_median_failed")
    accepted, unresolved = build_consensus([
        item("emotion:happy", 1),
        item("emotion:happy", 2),
        item("emotion:surprised", 2),
    ])
    require(not accepted and len(unresolved) == 1, "deliberate_disagreement_accepted")
    accepted, unresolved = build_consensus([
        item("emotion:happy", 1),
        item("emotion:surprised", 2),
        item("emotion:confused", 2),
    ])
    require(not accepted and len(unresolved) == 1, "consensus_disagreement_accepted")


def check_logo() -> None:
    data = (ROOT / "logo.png").read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), "logo_not_png")
    width, height = struct.unpack(">II", data[16:24])
    require((width, height) == (512, 512), f"logo_size={(width, height)}")


if __name__ == "__main__":
    main()
