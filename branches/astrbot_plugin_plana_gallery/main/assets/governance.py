from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from .constants import REVIEW_TAG, SAFE_TAG
from .tag_governance import GOVERNANCE_VERSION, governance_rule_map


class GalleryGovernanceMixin:
    def initialize_governance(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_tag_governance_batches (
                batch_id TEXT PRIMARY KEY,
                governance_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                completed_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS gallery_tag_governance_audit (
                event_key TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                asset_id INTEGER NOT NULL,
                asset_ref TEXT NOT NULL,
                source_tag TEXT NOT NULL,
                mode TEXT NOT NULL,
                added_tags_json TEXT NOT NULL DEFAULT '[]',
                emotion_profiles_json TEXT NOT NULL DEFAULT '[]',
                action TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(asset_id) REFERENCES gallery_assets(id) ON DELETE CASCADE,
                FOREIGN KEY(batch_id) REFERENCES gallery_tag_governance_batches(batch_id)
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_governance_audit_asset
                ON gallery_tag_governance_audit(asset_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_gallery_governance_audit_source
                ON gallery_tag_governance_audit(source_tag, action);
            """
        )

    def governance_status(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if not self._table_exists(conn, "gallery_tag_governance_audit"):
            return {"audited_assets": 0, "audit_events": 0, "last_batch": None}
        audit_events = int(conn.execute(
            "SELECT COUNT(*) FROM gallery_tag_governance_audit"
        ).fetchone()[0])
        audited_assets = int(conn.execute(
            "SELECT COUNT(DISTINCT asset_id) FROM gallery_tag_governance_audit"
        ).fetchone()[0])
        batch = conn.execute(
            """SELECT batch_id, governance_version, status, summary_json,
                      created_at, completed_at
               FROM gallery_tag_governance_batches
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        last_batch = dict(batch) if batch else None
        if last_batch:
            last_batch["summary"] = json.loads(last_batch.pop("summary_json") or "{}")
        return {"audited_assets": audited_assets, "audit_events": audit_events,
                "last_batch": last_batch}

    def govern_legacy_tags(
        self, *, apply: bool = False, batch_id: str = ""
    ) -> dict[str, Any]:
        rules = governance_rule_map()
        with self._connect() as conn:
            rows = self._legacy_governance_rows(conn, set(rules))
            plan = [self._governance_plan_item(row, rules[str(row["source_tag"])])
                    for row in rows]
            summary = self._governance_summary(plan)
            if not apply:
                return {"ok": True, "applied": False, "summary": summary, "assets": plan}

            self.initialize_governance(conn)
            actual_batch_id = batch_id.strip()[:120] or (
                f"legacy-v{GOVERNANCE_VERSION}-{self._now()}-{uuid.uuid4().hex[:8]}"
            )
            now = self._now()
            conn.execute(
                """INSERT INTO gallery_tag_governance_batches
                   (batch_id, governance_version, status, summary_json, created_at)
                   VALUES (?, ?, 'running', '{}', ?)""",
                (actual_batch_id, GOVERNANCE_VERSION, now),
            )
            changed_assets: set[int] = set()
            inserted_audits = 0
            for item in plan:
                changed, audited = self._apply_governance_item(
                    conn, item, actual_batch_id, now
                )
                if changed:
                    changed_assets.add(int(item["asset_id"]))
                inserted_audits += int(audited)
            for asset_id in changed_assets:
                self.refresh_search_index(conn, asset_id)
            applied_summary = {
                **summary, "changed_assets": len(changed_assets),
                "new_audit_events": inserted_audits,
            }
            conn.execute(
                """UPDATE gallery_tag_governance_batches
                   SET status='succeeded', summary_json=?, completed_at=?
                   WHERE batch_id=?""",
                (json.dumps(applied_summary, ensure_ascii=False), self._now(), actual_batch_id),
            )
            return {"ok": True, "applied": True, "batch_id": actual_batch_id,
                    "summary": applied_summary, "assets": plan}

    def _legacy_governance_rows(
        self, conn: sqlite3.Connection, governed_tags: set[str]
    ) -> list[dict[str, Any] | sqlite3.Row]:
        if self._table_exists(conn, "gallery_asset_tags"):
            return list(conn.execute(
                """SELECT a.id, a.asset_ref, a.tags, t.tag AS source_tag
                   FROM gallery_asset_tags t
                   JOIN gallery_assets a ON a.id=t.asset_id
                   WHERE t.tag IN ({})
                   ORDER BY a.id, t.tag""".format(
                       ",".join("?" for _ in governed_tags)
                   ),
                tuple(sorted(governed_tags)),
            ).fetchall())
        rows: list[dict[str, Any]] = []
        for asset in conn.execute(
            "SELECT id, asset_ref, tags FROM gallery_assets ORDER BY id"
        ).fetchall():
            for tag in self._json_list(str(asset["tags"])):
                if tag in governed_tags:
                    rows.append({
                        "id": int(asset["id"]), "asset_ref": str(asset["asset_ref"]),
                        "tags": str(asset["tags"]), "source_tag": tag,
                    })
        return rows

    def _apply_governance_item(
        self, conn: sqlite3.Connection, item: dict[str, Any], batch_id: str, now: int
    ) -> tuple[bool, bool]:
        asset_id = int(item["asset_id"])
        current = conn.execute(
            "SELECT tags FROM gallery_assets WHERE id=?", (asset_id,)
        ).fetchone()
        if not current:
            return False, False
        tags = self._json_list(str(current["tags"]))
        desired = [tag for tag in tags if tag not in item["removed_tags"]]
        desired.extend(tag for tag in item["added_tags"] if tag not in desired)
        if item["requires_review"]:
            desired = [tag for tag in desired if tag != SAFE_TAG]
            if REVIEW_TAG not in desired:
                desired.append(REVIEW_TAG)
        changed = desired != tags
        if changed:
            tags = desired
            conn.execute(
                "UPDATE gallery_assets SET tags=?, updated_at=? WHERE id=?",
                (json.dumps(tags, ensure_ascii=False), now, asset_id),
            )
            self.replace_asset_tags(conn, asset_id, tags)
        profiles = item["emotion_profiles"]
        if profiles:
            before = self.emotions_for_asset(asset_id, conn)
            merged = {str(value["emotion_tag"]): value for value in before}
            for value in profiles:
                merged[str(value["emotion_tag"])] = value
            desired = self._normalize_emotions(
                list(merged.values()),
                [tag for tag in tags if tag.startswith("emotion:")],
                tags,
            )
            if _emotion_signature(before) != _emotion_signature(desired):
                self.replace_asset_emotions(conn, asset_id, tags, profiles, merge=True)
                changed = True
        cursor = conn.execute(
            """INSERT OR IGNORE INTO gallery_tag_governance_audit
               (event_key, batch_id, asset_id, asset_ref, source_tag, mode,
                added_tags_json, emotion_profiles_json, action, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self._governance_event_key(item), batch_id, asset_id, item["asset_ref"],
                item["source_tag"], item["mode"],
                json.dumps(item["added_tags"], ensure_ascii=False),
                json.dumps(profiles, ensure_ascii=False), item["action"], now,
            ),
        )
        return changed, cursor.rowcount == 1

    def _governance_plan_item(
        self, row: sqlite3.Row | dict[str, Any], rule: dict[str, Any]
    ) -> dict[str, Any]:
        source_tag = str(row["source_tag"])
        current_tags = self._json_list(str(row["tags"]))
        auto_apply = bool(rule["auto_apply"])
        targets = list(rule["targets"])
        classified = any(
            tag.startswith(("emotion:", "tone:", "scene:"))
            for tag in current_tags
        )
        keep_free_tag = str(rule["mode"]) == "keep"
        normalized = auto_apply or (bool(rule["requires_review"]) and classified)
        added_tags = targets if auto_apply else []
        removed_tags = [source_tag] if normalized and not keep_free_tag else []
        requires_review = bool(rule["requires_review"]) and not classified
        profiles = [
            {"emotion_tag": target, "intensity": int(rule["default_intensity"] or 2),
             "prominence": "primary", "source": "legacy-normalized",
             "suggestion_confidence": None}
            for target in added_tags if target.startswith("emotion:")
        ]
        action = "normalized" if auto_apply else (
            "normalized_existing" if normalized else (
                "queued_review" if requires_review else "kept"
            )
        )
        return {
            "asset_id": int(row["id"]), "asset_ref": str(row["asset_ref"]),
            "source_tag": source_tag, "mode": str(rule["mode"]),
            "targets": targets, "added_tags": added_tags, "removed_tags": removed_tags,
            "emotion_profiles": profiles, "requires_review": requires_review,
            "action": action, "rationale": str(rule["rationale"]),
        }

    @staticmethod
    def _governance_summary(plan: list[dict[str, Any]]) -> dict[str, Any]:
        actions: dict[str, int] = {}
        source_tags: dict[str, int] = {}
        for item in plan:
            actions[item["action"]] = actions.get(item["action"], 0) + 1
            source_tags[item["source_tag"]] = source_tags.get(item["source_tag"], 0) + 1
        return {
            "governance_version": GOVERNANCE_VERSION,
            "matched_relations": len(plan),
            "matched_assets": len({item["asset_id"] for item in plan}),
            "actions": dict(sorted(actions.items())),
            "source_tags": dict(sorted(source_tags.items())),
        }

    @staticmethod
    def _governance_event_key(item: dict[str, Any]) -> str:
        raw = f"v{GOVERNANCE_VERSION}:{item['asset_ref']}:{item['source_tag']}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None


def _emotion_signature(values: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (
            str(value.get("emotion_tag") or ""), int(value.get("intensity") or 2),
            str(value.get("prominence") or "secondary"),
            str(value.get("source") or "manual"), value.get("suggestion_confidence"),
        )
        for value in values
    )
