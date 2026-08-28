from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def main() -> None:
    from astrbot_plugin_plana_gallery.assets.store import GalleryStore

    with tempfile.TemporaryDirectory() as tmp:
        store = GalleryStore(tmp)
        store.initialize()
        fixture = store.asset_dir / "fixture.png"
        fixture.write_bytes(b"\x89PNG\r\n\x1a\nbenchmark")
        now = store._now()
        with store._connect() as conn:
            rows = []
            tag_rows = []
            for index in range(20_000):
                asset_id = index + 1
                tags = ["emotion:happy", "tone:agree", "safety:safe"]
                rows.append((asset_id, f"gallery:{index:016x}", f"{index:064x}", str(fixture), "image/png", f"asset {index}", "开心赞同", json.dumps(tags), now-index, now-index))
                tag_rows.extend((asset_id, tag) for tag in tags)
            conn.executemany(
                """INSERT INTO gallery_assets
                   (id, asset_ref, sha256, file_path, mime_type, title, caption, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.executemany(
                "INSERT INTO gallery_asset_tags(asset_id, tag) VALUES (?, ?)", tag_rows
            )
            store.refresh_search_index(conn)
        started = perf_counter()
        candidates = store.chat_candidates(
            request_id="benchmark", query="开心", facets=["emotion:happy"],
            exclude_asset_refs=[], limit=6,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        if len(candidates) != 6:
            raise SystemExit(f"candidate_count={len(candidates)}")
        print(f"gallery_candidate_20k_ms={elapsed_ms:.2f}")


if __name__ == "__main__":
    main()
