from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_gallery.assets.constants import DEFAULT_ALIASES, DEFAULT_TAGS  # noqa: E402
from astrbot_plugin_plana_gallery.web.page import gallery_html  # noqa: E402

DIRECT_PROJECTION = {
    "happy": "emotion:happy", "surprised": "emotion:surprised",
    "confused": "emotion:confused", "shy": "emotion:shy",
    "sad": "emotion:sad", "angry": "emotion:angry",
    "like": "tone:agree", "morning": "scene:greeting", "see": "scene:wait",
}


def json_tags(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data if str(item).strip()] if isinstance(data, list) else []


def serialize_asset(
    row: sqlite3.Row, emotions: list[dict[str, object]] | None = None
) -> dict[str, object]:
    file_path = Path(str(row["file_path"] or ""))
    return {
        "id": int(row["id"]), "asset_ref": str(row["asset_ref"]),
        "sha256": str(row["sha256"]), "file_path": str(file_path),
        "original_path": str(row["original_path"] or ""),
        "mime_type": str(row["mime_type"] or ""), "title": str(row["title"] or ""),
        "caption": str(row["caption"] or ""), "tags": json_tags(str(row["tags"] or "[]")),
        "emotions": emotions or [], "source": str(row["source"] or ""),
        "created_at": int(row["created_at"]), "updated_at": int(row["updated_at"]),
        "file_valid": file_path.is_file(),
    }


def definitions(counter: Counter[str]) -> list[dict[str, object]]:
    return [
        {"tag": tag, "facet": facet.lower(), "label": label,
         "description": description, "managed": 1, "asset_count": counter.get(tag, 0)}
        for tag, facet, label, description in DEFAULT_TAGS
    ]


def aliases() -> list[dict[str, str]]:
    return [
        {"alias": alias, "canonical_tag": canonical}
        for alias, canonical in sorted(DEFAULT_ALIASES.items())
    ]


def projected_tags(tags: list[str]) -> list[str]:
    result = list(tags)
    for tag in tags:
        canonical = DIRECT_PROJECTION.get(tag)
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def projected_emotions(tags: list[str]) -> list[dict[str, object]]:
    values = [tag for tag in projected_tags(tags) if tag.startswith("emotion:")]
    return [
        {"emotion_tag": tag, "intensity": 2,
         "prominence": "primary" if index == 0 else "secondary",
         "source": "preview-projection", "suggestion_confidence": None}
        for index, tag in enumerate(values[:2])
    ]


def handler_for(database: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def connect(self) -> sqlite3.Connection:
            conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn

        def all_assets(self, conn: sqlite3.Connection) -> list[dict[str, object]]:
            tables = {str(row[0]) for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            profiles: dict[int, list[dict[str, object]]] = {}
            if "gallery_asset_emotions" in tables:
                for row in conn.execute(
                    """SELECT asset_id, emotion_tag, intensity, prominence, source,
                              suggestion_confidence
                       FROM gallery_asset_emotions
                       ORDER BY asset_id, prominence DESC, emotion_tag"""
                ):
                    profiles.setdefault(int(row["asset_id"]), []).append({
                        "emotion_tag": str(row["emotion_tag"]),
                        "intensity": int(row["intensity"]),
                        "prominence": str(row["prominence"]),
                        "source": str(row["source"]),
                        "suggestion_confidence": row["suggestion_confidence"],
                    })
            return [serialize_asset(row, profiles.get(int(row["id"]))) for row in conn.execute(
                "SELECT * FROM gallery_assets ORDER BY updated_at DESC, id DESC"
            ).fetchall()]

        def schema_version(self, conn: sqlite3.Connection) -> int:
            try:
                row = conn.execute(
                    "SELECT value FROM gallery_schema_meta WHERE key='schema_version'"
                ).fetchone()
            except sqlite3.OperationalError:
                return 0
            return int(row[0]) if row else 0

        def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, data: dict[str, object], status: int = 200) -> None:
            self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode(),
                            "application/json; charset=utf-8")

        def body_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            try:
                value = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}
            return value if isinstance(value, dict) else {}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/dashboard"}:
                self.send_bytes(200, gallery_html("/api").encode(), "text/html; charset=utf-8")
                return
            with self.connect() as conn:
                assets = self.all_assets(conn)
                counter = Counter(tag for asset in assets for tag in asset["tags"])
                taxonomy = definitions(counter)
                tag_aliases = aliases()
                orphaned = sorted(tag for tag in counter if ":" not in tag and tag != "needs-review")
                if parsed.path == "/api/api/status":
                    self.send_json({"ok": True, "assets": len(assets),
                        "review_assets": counter.get("needs-review", 0), "tags": len(counter),
                        "tag_list": sorted(counter), "tag_counts": dict(counter),
                        "definitions": taxonomy, "aliases": tag_aliases,
                        "orphaned_tags": orphaned, "fts_available": False,
                        "schema_version": self.schema_version(conn),
                        "preview_read_only": True})
                    return
                if parsed.path == "/api/api/tags":
                    self.send_json({"ok": True, "definitions": taxonomy, "aliases": tag_aliases,
                                    "orphaned_tags": orphaned, "fts_available": False,
                                    "preview_read_only": True})
                    return
                if parsed.path == "/api/api/jobs":
                    self.send_json({"ok": True, "counts": {}, "jobs": []})
                    return
                if parsed.path == "/api/api/assets":
                    self.serve_assets(assets, parse_qs(parsed.query))
                    return
                if parsed.path.startswith("/api/api/assets/thumbnail/") or parsed.path.startswith("/api/api/assets/file/"):
                    self.serve_file(conn, parsed.path)
                    return
            self.send_json({"ok": False, "error": "not_found"}, 404)

        def serve_assets(self, assets: list[dict[str, object]], query: dict[str, list[str]]) -> None:
            search = (query.get("q") or [""])[0].strip().lower()
            selected = [tag for tag in (query.get("tags") or [""])[0].lower().split(",") if tag]
            mode = (query.get("tag_mode") or ["all"])[0]
            review = (query.get("review") or ["all"])[0]
            source = (query.get("source") or [""])[0]
            page = max(1, int((query.get("page") or ["1"])[0]))
            size = max(12, min(120, int((query.get("page_size") or ["48"])[0])))
            filtered = []
            for asset in assets:
                asset_tags = list(asset["tags"])
                haystack = " ".join([str(asset["title"]), str(asset["caption"]),
                                     str(asset["asset_ref"]), *asset_tags]).lower()
                if search and search not in haystack:
                    continue
                if selected and mode == "all" and not all(tag in asset_tags for tag in selected):
                    continue
                if selected and mode == "any" and not any(tag in asset_tags for tag in selected):
                    continue
                if review == "pending" and "needs-review" not in asset_tags:
                    continue
                if review == "ready" and "needs-review" in asset_tags:
                    continue
                if source and asset["source"] != source:
                    continue
                filtered.append(asset)
            total = len(filtered)
            page_count = max(1, math.ceil(total / size))
            page = min(page, page_count)
            start = (page - 1) * size
            sources = Counter(str(asset["source"]) for asset in assets if asset["source"])
            self.send_json({"ok": True, "assets": filtered[start:start + size], "total": total,
                            "page": page, "page_size": size, "page_count": page_count,
                            "sources": [{"source": key, "count": count}
                                        for key, count in sources.most_common()]})

        def serve_file(self, conn: sqlite3.Connection, path: str) -> None:
            try:
                asset_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self.send_json({"ok": False, "error": "invalid_asset_id"}, 400)
                return
            row = conn.execute("SELECT file_path, mime_type FROM gallery_assets WHERE id=?",
                               (asset_id,)).fetchone()
            if not row:
                self.send_json({"ok": False, "error": "not_found"}, 404)
                return
            file_path = Path(str(row["file_path"]))
            if not file_path.is_file():
                self.send_json({"ok": False, "error": "file_missing"}, 404)
                return
            self.send_bytes(200, file_path.read_bytes(),
                            str(row["mime_type"] or "application/octet-stream"))

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path == "/api/api/diagnostics/query":
                self.serve_diagnostics(self.body_json())
                return
            self.send_json({"ok": False, "error": "preview_read_only"}, 403)

        def serve_diagnostics(self, payload: dict[str, object]) -> None:
            search = str(payload.get("query") or "").lower()
            facets = [str(item).lower() for item in payload.get("facets", [])]
            requested = [item for item in payload.get("emotions", []) if isinstance(item, dict)]
            excluded = set(payload.get("exclude_asset_refs") or [])
            candidates = []
            exclusions = []
            with self.connect() as conn:
                for asset in self.all_assets(conn):
                    if asset["asset_ref"] in excluded:
                        exclusions.append({"asset_ref": asset["asset_ref"], "reason": "explicit_exclusion"})
                        continue
                    tags = list(asset["tags"])
                    projected = projected_tags(tags)
                    matched = [tag for tag in facets if tag in projected]
                    matched_emotions = [str(item.get("emotion_tag") or "") for item in requested
                                        if str(item.get("emotion_tag") or "") in projected]
                    text = " ".join([str(asset["title"]), str(asset["caption"]), *tags]).lower()
                    facet_score = len(matched) * 35
                    emotion_score = len(matched_emotions) * 30
                    text_score = 8 if search and any(word in text for word in search.split()) else 0
                    score = facet_score + emotion_score + text_score
                    if score:
                        candidates.append({"asset_id": asset["id"], "asset_ref": asset["asset_ref"],
                            "caption": asset["caption"], "tags": projected,
                            "emotions": projected_emotions(tags), "matched_facets": matched,
                            "matched_emotions": matched_emotions, "score": score,
                            "score_breakdown": {"facet": facet_score,
                                "emotion_coverage": emotion_score, "intensity_match": 0,
                                "primary_alignment": 0, "emotion_conflict_penalty": 0,
                                "text": text_score}})
            candidates.sort(key=lambda row: int(row["score"]), reverse=True)
            candidates = candidates[:6]
            top = candidates[0] if candidates else None
            second = int(candidates[1]["score"]) if len(candidates) > 1 else 0
            direct = bool(top and (top["matched_emotions"] or top["matched_facets"])
                          and int(top["score"]) >= 50 and int(top["score"]) - second >= 12)
            self.send_json({"ok": True, "request_id": str(payload.get("request_id") or "preview"),
                "candidates": candidates, "exclusions": exclusions[:100],
                "selection_hint": {"mode": "direct" if direct else "model_or_none",
                    "asset_ref": str(top["asset_ref"]) if direct and top else "",
                    "score": int(top["score"]) if top else 0,
                    "margin": int(top["score"]) - second if top else 0}})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only Gallery Web preview")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=6198, type=int)
    args = parser.parse_args()
    if not args.database.is_file():
        raise SystemExit(f"database_missing={args.database}")
    ThreadingHTTPServer((args.host, args.port), handler_for(args.database)).serve_forever()


if __name__ == "__main__":
    main()
