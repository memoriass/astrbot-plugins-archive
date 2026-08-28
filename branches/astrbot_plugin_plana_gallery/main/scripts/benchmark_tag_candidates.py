from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_gallery.assets.semantic import tag_candidate  # noqa: E402


def main() -> None:
    cases = json.loads((ROOT / "benchmarks" / "tag_candidates.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        candidate = tag_candidate(case["asset"], set(case["known_tags"]))
        semantic = candidate["semantic_candidate"]
        ok = (
            semantic["matched_tags"] == case["expected_tags"]
            and semantic["review_status"] == case["review_status"]
            and semantic["candidate_only"] is True
        )
        results.append({"id": case["id"], "ok": ok, "candidate": semantic})
    payload = {"ok": all(item["ok"] for item in results), "results": results}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
