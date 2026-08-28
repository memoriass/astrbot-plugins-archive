from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


THUMBNAIL_SIZES = (320, 640)
JOB_RETRY_DELAYS = (5, 30, 120)
JOB_MAX_ATTEMPTS = len(JOB_RETRY_DELAYS)
RUNNING_STALE_SECONDS = 600
SUCCEEDED_RETENTION_SECONDS = 7 * 86400
FAILED_RETENTION_SECONDS = 30 * 86400


class AssetDerivativeMixin:
    def initialize_derivatives(self, conn: Any) -> None:
        self.thumbnail_dir = self.root / "thumbnails"
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gallery_asset_derivatives (
                asset_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                size INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                source_mtime_ns INTEGER NOT NULL DEFAULT 0,
                source_size INTEGER NOT NULL DEFAULT 0,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ready',
                generated_at INTEGER NOT NULL,
                PRIMARY KEY(asset_id, kind, size),
                FOREIGN KEY(asset_id) REFERENCES gallery_assets(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS gallery_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL UNIQUE,
                job_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                available_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                started_at INTEGER NOT NULL DEFAULT 0,
                finished_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_gallery_jobs_status
                ON gallery_jobs(status, available_at, created_at, id);
            """
        )
        self._ensure_column(conn, "gallery_asset_derivatives", "source_mtime_ns", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "gallery_asset_derivatives", "source_size", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "gallery_jobs", "available_at", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "gallery_jobs", "updated_at", "INTEGER NOT NULL DEFAULT 0")
        now = self._now()
        conn.execute(
            """UPDATE gallery_jobs SET status='pending', started_at=0,
               available_at=?, updated_at=?
               WHERE status='running' AND started_at < ?""",
            (now, now, now - RUNNING_STALE_SECONDS),
        )
        self._cleanup_jobs(conn, now)

    def enqueue_thumbnail_jobs(self) -> int:
        queued = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT id, sha256 FROM gallery_assets ORDER BY id").fetchall()
        for row in rows:
            for size in THUMBNAIL_SIZES:
                queued += int(self.enqueue_thumbnail_job(int(row["id"]), size, str(row["sha256"])))
        return queued

    def enqueue_thumbnail_job(self, asset_id: int, size: int, source_sha256: str) -> bool:
        safe_size = min(THUMBNAIL_SIZES, key=lambda value: abs(value - int(size)))
        now = self._now()
        key = f"thumbnail:{asset_id}:{safe_size}:{source_sha256}"
        payload = json.dumps({"asset_id": asset_id, "size": safe_size}, separators=(",", ":"))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO gallery_jobs
                    (dedupe_key, job_type, payload, status, attempts, error,
                     available_at, created_at, updated_at)
                VALUES (?, 'thumbnail', ?, 'pending', 0, '', ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    status=CASE WHEN gallery_jobs.status='running' THEN 'running' ELSE 'pending' END,
                    attempts=CASE WHEN gallery_jobs.status='running' THEN gallery_jobs.attempts ELSE 0 END,
                    error=CASE WHEN gallery_jobs.status='running' THEN gallery_jobs.error ELSE '' END,
                    available_at=CASE WHEN gallery_jobs.status='running' THEN gallery_jobs.available_at ELSE excluded.available_at END,
                    finished_at=CASE WHEN gallery_jobs.status='running' THEN gallery_jobs.finished_at ELSE 0 END,
                    updated_at=excluded.updated_at
                """,
                (key, payload, now, now, now),
            )
        return cursor.rowcount > 0

    def thumbnail_status(self, asset_id: int, size: int = 320) -> dict[str, Any]:
        safe_size = min(THUMBNAIL_SIZES, key=lambda value: abs(value - int(size)))
        asset = self.get_asset(asset_id)
        if not asset:
            return {"ok": False, "error": "asset_not_found"}
        source = Path(str(asset["file_path"])).resolve()
        if not source.is_file() or not self._managed_file_valid(asset):
            return {"ok": False, "error": "asset_file_invalid"}
        stat = source.stat()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM gallery_asset_derivatives
                   WHERE asset_id=? AND kind='thumbnail' AND size=?""",
                (asset_id, safe_size),
            ).fetchone()
            if row:
                cached = Path(str(row["file_path"])).resolve()
                current = (
                    str(row["status"]) == "ready"
                    and int(row["source_mtime_ns"] or 0) == int(stat.st_mtime_ns)
                    and int(row["source_size"] or 0) == int(stat.st_size)
                    and cached.is_file()
                    and self.thumbnail_dir.resolve() in cached.parents
                )
                if current:
                    return {"ok": True, "ready": True, "path": cached, "mime_type": str(row["mime_type"])}
                conn.execute(
                    "UPDATE gallery_asset_derivatives SET status='stale' WHERE asset_id=? AND kind='thumbnail' AND size=?",
                    (asset_id, safe_size),
                )
        self.enqueue_thumbnail_job(asset_id, safe_size, str(asset["sha256"]))
        return {"ok": True, "ready": False, "status": "pending"}

    def process_next_job(self) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM gallery_jobs
                   WHERE status IN ('pending', 'retrying') AND available_at <= ?
                   ORDER BY available_at, created_at, id LIMIT 1""",
                (now,),
            ).fetchone()
            if not row:
                self._cleanup_jobs(conn, now)
                return None
            job_id = int(row["id"])
            cursor = conn.execute(
                """UPDATE gallery_jobs SET status='running', attempts=attempts+1,
                   started_at=?, error='', updated_at=?
                   WHERE id=? AND status IN ('pending', 'retrying')""",
                (now, now, job_id),
            )
            if cursor.rowcount != 1:
                return None
            attempts = int(row["attempts"] or 0) + 1
        try:
            payload = json.loads(str(row["payload"] or "{}"))
            if str(row["job_type"]) != "thumbnail":
                raise ValueError("job_type_unsupported")
            self.ensure_thumbnail(int(payload["asset_id"]), int(payload["size"]))
        except Exception as exc:
            retry = attempts < JOB_MAX_ATTEMPTS
            delay = JOB_RETRY_DELAYS[min(attempts - 1, len(JOB_RETRY_DELAYS) - 1)]
            finished_at = 0 if retry else self._now()
            with self._connect() as conn:
                conn.execute(
                    """UPDATE gallery_jobs SET status=?, error=?, available_at=?,
                       finished_at=?, updated_at=? WHERE id=?""",
                    (
                        "retrying" if retry else "failed", str(exc)[:500],
                        self._now() + delay if retry else 0, finished_at,
                        self._now(), job_id,
                    ),
                )
            return {"ok": False, "id": job_id, "retrying": retry, "error": str(exc)}
        with self._connect() as conn:
            conn.execute(
                """UPDATE gallery_jobs SET status='succeeded', finished_at=?,
                   updated_at=? WHERE id=?""",
                (self._now(), self._now(), job_id),
            )
        return {"ok": True, "id": job_id}

    def jobs_status(self, limit: int = 50) -> dict[str, Any]:
        with self._connect() as conn:
            counts = {
                str(row["status"]): int(row["count"])
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM gallery_jobs GROUP BY status"
                ).fetchall()
            }
            rows = conn.execute(
                "SELECT * FROM gallery_jobs ORDER BY id DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return {"ok": True, "counts": counts, "jobs": [dict(row) for row in rows]}

    def ensure_thumbnail(self, asset_id: int, size: int = 320) -> tuple[Path, str]:
        safe_size = min(THUMBNAIL_SIZES, key=lambda value: abs(value - int(size)))
        asset = self.get_asset(asset_id)
        if not asset:
            raise FileNotFoundError("asset_not_found")
        source = Path(str(asset["file_path"])).resolve()
        if not source.is_file() or not self._managed_file_valid(asset):
            raise FileNotFoundError("asset_file_invalid")
        stat = source.stat()
        source_sha256 = _file_sha256(source)
        target = self.thumbnail_dir / f"{source_sha256}-{safe_size}.webp"
        previous_path: Path | None = None
        with self._connect() as conn:
            previous = conn.execute(
                """SELECT file_path FROM gallery_asset_derivatives
                   WHERE asset_id=? AND kind='thumbnail' AND size=?""",
                (asset_id, safe_size),
            ).fetchone()
            if previous:
                previous_path = Path(str(previous["file_path"])).resolve()
        with Image.open(source) as image:
            image.seek(0)
            normalized = ImageOps.exif_transpose(image)
            normalized.thumbnail((safe_size, safe_size), Image.Resampling.LANCZOS)
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
            normalized.save(target, "WEBP", quality=82, method=4)
            width, height = normalized.size
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO gallery_asset_derivatives
                   (asset_id, kind, size, file_path, mime_type, source_sha256,
                    source_mtime_ns, source_size, width, height, status, generated_at)
                   VALUES (?, 'thumbnail', ?, ?, 'image/webp', ?, ?, ?, ?, ?, 'ready', ?)
                   ON CONFLICT(asset_id, kind, size) DO UPDATE SET
                     file_path=excluded.file_path, mime_type=excluded.mime_type,
                     source_sha256=excluded.source_sha256,
                     source_mtime_ns=excluded.source_mtime_ns,
                     source_size=excluded.source_size, width=excluded.width,
                     height=excluded.height, status='ready', generated_at=excluded.generated_at""",
                (
                    asset_id, safe_size, str(target), source_sha256,
                    int(stat.st_mtime_ns), int(stat.st_size), width, height, self._now(),
                ),
            )
        if previous_path and previous_path != target.resolve():
            try:
                if previous_path.is_file() and self.thumbnail_dir.resolve() in previous_path.parents:
                    previous_path.unlink()
            except OSError:
                pass
        return target, "image/webp"

    def derivative_facts(self, asset_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT size, width, height, status FROM gallery_asset_derivatives "
                "WHERE asset_id=? AND kind='thumbnail' ORDER BY size",
                (asset_id,),
            ).fetchall()
        return {"thumbnails": [dict(row) for row in rows]}

    def remove_derivative_files(self, asset_id: int) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT file_path FROM gallery_asset_derivatives WHERE asset_id=?",
                (asset_id,),
            ).fetchall()
        for row in rows:
            path = Path(str(row["file_path"])).resolve()
            try:
                if path.is_file() and self.thumbnail_dir.resolve() in path.parents:
                    path.unlink()
            except OSError:
                pass

    @staticmethod
    def _ensure_column(conn: Any, table: str, column: str, definition: str) -> None:
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _cleanup_jobs(conn: Any, now: int) -> None:
        conn.execute(
            "DELETE FROM gallery_jobs WHERE status='succeeded' AND finished_at > 0 AND finished_at < ?",
            (now - SUCCEEDED_RETENTION_SECONDS,),
        )
        conn.execute(
            "DELETE FROM gallery_jobs WHERE status='failed' AND finished_at > 0 AND finished_at < ?",
            (now - FAILED_RETENTION_SECONDS,),
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
