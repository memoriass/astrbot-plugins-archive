from __future__ import annotations
from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any
from ..remote.mappings import RemoteMappingMixin
from .chat_search import ChatSearchMixin
from .collection import AssetCollectionMixin
from .constants import IMAGE_SUFFIXES, REVIEW_TAG, SAFE_TAG
from .derivatives import AssetDerivativeMixin
from .emotions import AssetEmotionMixin
from .governance import GalleryGovernanceMixin
from .lifecycle import AssetLifecycleMixin
from .query import AssetQueryMixin
from .schema import GallerySchemaMixin
from .serialization import AssetSerializationMixin
from .tag_index import TagIndexMixin
from .transactions import GalleryTransactionMixin
class GalleryStore(
    RemoteMappingMixin,
    TagIndexMixin,
    AssetLifecycleMixin,
    AssetQueryMixin,
    GallerySchemaMixin,
    ChatSearchMixin,
    AssetDerivativeMixin,
    AssetEmotionMixin,
    GalleryGovernanceMixin,
    GalleryTransactionMixin,
    AssetSerializationMixin,
    AssetCollectionMixin,
):
    def __init__(self, data_dir: str, max_import_bytes: int = 52_428_800):
        self.root = Path(data_dir)
        self.db_path = self.root / "gallery.sqlite3"
        self.asset_dir = self.root / "assets"
        self.max_import_bytes = max(1, int(max_import_bytes))
    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gallery_assets (
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
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_assets_updated
                    ON gallery_assets(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_gallery_assets_source
                    ON gallery_assets(source);
                CREATE INDEX IF NOT EXISTS idx_gallery_assets_ref
                    ON gallery_assets(asset_ref);
                CREATE INDEX IF NOT EXISTS idx_gallery_assets_sha
                    ON gallery_assets(sha256);
                CREATE TABLE IF NOT EXISTS gallery_remote_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    remote_key TEXT NOT NULL DEFAULT '',
                    remote_url TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'uploaded',
                    error TEXT NOT NULL DEFAULT '',
                    uploaded_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(asset_id, provider),
                    FOREIGN KEY(asset_id) REFERENCES gallery_assets(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_remote_provider
                    ON gallery_remote_assets(provider, status);
                CREATE TABLE IF NOT EXISTS gallery_asset_tombstones (
                    asset_ref TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT 'deleted',
                    deleted_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gallery_candidate_feedback (
                    request_id TEXT PRIMARY KEY,
                    asset_ref TEXT NOT NULL,
                    action TEXT NOT NULL,
                    query TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gallery_feedback_asset
                    ON gallery_candidate_feedback(asset_ref, created_at DESC);
                CREATE TABLE IF NOT EXISTS gallery_review_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_ref TEXT NOT NULL,
                    before_tags TEXT NOT NULL,
                    after_tags TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            self.ensure_tag_index(conn)
            self.initialize_local_schema(conn)
            self.initialize_emotions(conn)
            self.initialize_derivatives(conn)
            self.initialize_governance(conn)
            self.initialize_chat_collection(conn)
        self.enqueue_thumbnail_jobs()
    def import_asset(
        self,
        source_path: str,
        *,
        title: str = "",
        caption: str = "",
        tags: list[str] | None = None,
        source: str = "manual",
        keep_original_path: bool = True,
    ) -> dict[str, Any]:
        normalized_tags = self._reviewed_tags(
            self.canonicalize_tags(_normalize_tags(tags or [])) or [REVIEW_TAG]
        )
        path = Path(source_path).expanduser()
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": "file_not_found"}
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            return {"ok": False, "error": "unsupported_image_type"}
        size = path.stat().st_size
        if size > self.max_import_bytes:
            return {"ok": False, "error": "file_too_large", "size": size}
        digest = self._sha256(path)
        suffix = path.suffix.lower()
        managed_path = self.asset_dir / f"{digest}{suffix}"
        created_file = not managed_path.exists()
        if created_file:
            try:
                shutil.copy2(path, managed_path)
            except OSError as exc:
                return {"ok": False, "error": "asset_file_write_failed", "detail": str(exc)}
        mime_type = mimetypes.guess_type(str(managed_path))[0] or "application/octet-stream"
        try:
            return self._upsert_asset(
                digest=digest, managed_path=managed_path, mime_type=mime_type,
                original_path=str(path) if keep_original_path else "", title=title,
                caption=caption, tags=normalized_tags, source=source)
        except sqlite3.Error as exc:
            if created_file:
                managed_path.unlink(missing_ok=True)
            return {"ok": False, "error": "asset_database_write_failed", "detail": str(exc)}

    def import_bytes(
        self,
        content: bytes,
        *,
        filename: str = "",
        title: str = "",
        caption: str = "",
        tags: list[str] | None = None,
        source: str = "upload",
        original_path: str = "",
    ) -> dict[str, Any]:
        normalized_tags = self._reviewed_tags(
            self.canonicalize_tags(_normalize_tags(tags or [])) or [REVIEW_TAG]
        )
        if not content:
            return {"ok": False, "error": "empty_file"}
        if len(content) > self.max_import_bytes:
            return {"ok": False, "error": "file_too_large", "size": len(content)}
        detected = _detect_image_type(content)
        if detected is None:
            return {"ok": False, "error": "unsupported_image_type"}
        suffix, mime_type = detected
        digest = hashlib.sha256(content).hexdigest()
        managed_path = self.asset_dir / f"{digest}{suffix}"
        created_file = not managed_path.exists()
        if created_file:
            try:
                managed_path.write_bytes(content)
            except OSError as exc:
                return {"ok": False, "error": "asset_file_write_failed", "detail": str(exc)}
        try:
            return self._upsert_asset(
                digest=digest, managed_path=managed_path, mime_type=mime_type,
                original_path=original_path[:1000], title=title or Path(filename).stem,
                caption=caption, tags=normalized_tags, source=source,
            )
        except sqlite3.Error as exc:
            if created_file:
                managed_path.unlink(missing_ok=True)
            return {"ok": False, "error": "asset_database_write_failed", "detail": str(exc)}

    def _upsert_asset(
        self,
        *,
        digest: str,
        managed_path: Path,
        mime_type: str,
        original_path: str,
        title: str,
        caption: str,
        tags: list[str],
        source: str,
    ) -> dict[str, Any]:
        now = self._now()
        asset_ref = f"gallery:{digest[:16]}"
        new_tags = self._reviewed_tags(self.canonicalize_tags(_normalize_tags(tags)))
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM gallery_assets WHERE sha256=?", (digest,)
            ).fetchone()
            if existing:
                merged_tags = _merge_tags(_json_list(existing["tags"]), new_tags)
                conn.execute(
                    """UPDATE gallery_assets
                       SET title=?, caption=?, tags=?, source=?, original_path=?,
                           file_path=?, mime_type=?, updated_at=?
                       WHERE sha256=?""",
                    (
                        (title[:160] or existing["title"]),
                        (caption[:2000] or existing["caption"]),
                        json.dumps(merged_tags, ensure_ascii=False),
                        (source[:120] or existing["source"]),
                        (original_path or existing["original_path"]),
                        str(managed_path),
                        mime_type,
                        now,
                        digest,
                    ),
                )
                asset_id = int(existing["id"])
                self.replace_asset_tags(conn, asset_id, merged_tags)
                self.replace_asset_emotions(conn, asset_id, merged_tags)
                self.refresh_search_index(conn, asset_id)
                created = False
            else:
                cursor = conn.execute(
                    """INSERT INTO gallery_assets
                       (asset_ref, sha256, file_path, original_path, mime_type, title,
                        caption, tags, source, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_ref,
                        digest,
                        str(managed_path),
                        original_path,
                        mime_type,
                        title[:160],
                        caption[:2000],
                        json.dumps(new_tags, ensure_ascii=False),
                        source[:120],
                        now,
                        now,
                    ),
                )
                asset_id = int(cursor.lastrowid)
                self.replace_asset_tags(conn, asset_id, new_tags)
                self.replace_asset_emotions(conn, asset_id, new_tags)
                self.refresh_search_index(conn, asset_id)
                created = True
        return {"ok": True, "created": created, "asset": self.get_asset(asset_id)}
    def update_asset(
        self,
        asset_id: int,
        *,
        title: str | None = None,
        caption: str | None = None,
        tags: list[str] | None = None,
        emotions: list[dict[str, Any]] | None = None,
        approve: bool = False,
        expected_updated_at: int = 0,
    ) -> dict[str, Any]:
        current = self.get_asset(asset_id)
        if not current:
            return {"ok": False, "error": "not_found"}
        if expected_updated_at and int(current["updated_at"]) != int(expected_updated_at):
            return {"ok": False, "error": "version_conflict"}
        new_title = current["title"] if title is None else title[:160]
        new_caption = current["caption"] if caption is None else caption[:2000]
        new_tags = list(current["tags"])
        explicit_review_tags = [
            tag
            for tag in current["tags"]
            if tag == REVIEW_TAG or tag.startswith("safety:")
        ]
        with self._connect() as conn:
            indexed_review_tags = [
                str(row["tag"])
                for row in conn.execute(
                    """SELECT tag FROM gallery_asset_tags
                       WHERE asset_id=? AND (tag=? OR tag LIKE 'safety:%')""",
                    (asset_id, REVIEW_TAG),
                ).fetchall()
            ]
        if tags is not None:
            new_tags = self.canonicalize_tags(_normalize_tags(tags))
            if not any(
                tag == REVIEW_TAG or tag.startswith("safety:") for tag in new_tags
            ):
                new_tags = _merge_tags(new_tags, explicit_review_tags)
        if approve:
            new_tags = [
                tag for tag in new_tags if tag != REVIEW_TAG and tag != SAFE_TAG
            ]
            if not any(tag.startswith("safety:") for tag in new_tags):
                new_tags.append(SAFE_TAG)
        new_tags = self.project_emotion_intensity(new_tags, emotions)
        if not new_tags:
            return {"ok": False, "error": "missing_tags"}
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE gallery_assets
                   SET title=?, caption=?, tags=?, updated_at=?
                   WHERE id=? AND (?=0 OR updated_at=?)""",
                (
                    new_title,
                    new_caption,
                    json.dumps(new_tags, ensure_ascii=False),
                    max(self._now(), int(current["updated_at"]) + 1),
                    asset_id,
                    int(expected_updated_at),
                    int(expected_updated_at),
                ),
            )
            if cursor.rowcount != 1:
                return {"ok": False, "error": "version_conflict"}
            index_tags = new_tags
            if not approve and not any(
                tag == REVIEW_TAG or tag.startswith("safety:") for tag in new_tags
            ):
                index_tags = _merge_tags(new_tags, indexed_review_tags)
            self.replace_asset_tags(conn, asset_id, index_tags)
            self.replace_asset_emotions(conn, asset_id, index_tags, emotions)
            self.record_review_change(conn, current, new_tags)
            self.refresh_search_index(conn, asset_id)
        return {"ok": True, "asset": self.get_asset(asset_id)}

    def get_asset(self, asset_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gallery_assets WHERE id=?", (asset_id,)
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def get_asset_by_ref(self, asset_ref: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM gallery_assets WHERE asset_ref=?", (asset_ref,)
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def delete_asset(self, asset_id: int) -> dict[str, Any]:
        asset = self.get_asset(asset_id)
        if not asset:
            return {"ok": False, "error": "not_found"}
        self.remove_derivative_files(asset_id)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO gallery_asset_tombstones
                   (asset_ref, sha256, reason, deleted_at)
                   VALUES (?, ?, 'deleted', ?)
                   ON CONFLICT(asset_ref) DO UPDATE SET
                       sha256=excluded.sha256,
                       reason=excluded.reason,
                       deleted_at=excluded.deleted_at""",
                (asset["asset_ref"], asset["sha256"], self._now()),
            )
            conn.execute("DELETE FROM gallery_assets WHERE id=?", (asset_id,))
            if self.fts_available:
                conn.execute(
                    "DELETE FROM gallery_assets_fts WHERE asset_ref=?",
                    (str(asset["asset_ref"]),),
                )
        path = Path(str(asset["file_path"]))
        removed_file = False
        try:
            if path.exists() and path.is_file() and path.parent == self.asset_dir:
                path.unlink()
                removed_file = True
        except OSError:
            removed_file = False
        return {"ok": True, "asset": asset, "removed_file": removed_file}

    def delete_assets(self, asset_ids: list[int]) -> dict[str, Any]:
        deleted: list[dict[str, Any]] = []
        missing: list[int] = []
        for asset_id in dict.fromkeys(int(item) for item in asset_ids):
            result = self.delete_asset(asset_id)
            if result.get("ok"):
                deleted.append(result["asset"])
            else:
                missing.append(asset_id)
        return {
            "ok": True,
            "deleted": deleted,
            "missing": missing,
            "deleted_count": len(deleted),
            "missing_count": len(missing),
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM gallery_assets").fetchone()[0]
            tagged_assets = conn.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM gallery_asset_tags"
            ).fetchone()[0]
            tag_counts = self.indexed_tag_counts(conn)
        remote_counts = self.remote_counts()
        return {
            "ok": True,
            "assets": int(count),
            "tagged_assets": tagged_assets,
            "untagged_assets": max(0, int(count) - tagged_assets),
            "review_assets": int(tag_counts.get(REVIEW_TAG, 0)),
            "tags": len(tag_counts),
            "tag_list": sorted(tag_counts),
            "tag_counts": dict(sorted(tag_counts.items())),
            "remote": remote_counts,
        }

    def file_for_asset(self, asset_id: int) -> tuple[Path, str] | None:
        asset = self.get_asset(asset_id)
        if not asset:
            return None
        path = Path(str(asset["file_path"]))
        if not path.exists() or not path.is_file():
            return None
        return path, str(asset["mime_type"] or "application/octet-stream")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _now(self) -> int:
        return int(time.time())

    @staticmethod
    def _reviewed_tags(tags: list[str]) -> list[str]:
        if REVIEW_TAG not in tags and not any(tag.startswith("safety:") for tag in tags):
            return [*tags, SAFE_TAG]
        return tags

    def _json_list(self, value: str) -> list[str]:
        return _json_list(value)
def _normalize_tags(tags: list[str]) -> list[str]:
    return _merge_tags([], tags)


def _merge_tags(existing: list[str], incoming: list[str]) -> list[str]:
    result = []
    for tag in [*existing, *incoming]:
        text = str(tag).strip().lower()
        if text and text not in result:
            result.append(text[:80])
    return result[:80]
def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]
def _detect_image_type(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if content.startswith(b"BM"):
        return ".bmp", "image/bmp"
    return None
