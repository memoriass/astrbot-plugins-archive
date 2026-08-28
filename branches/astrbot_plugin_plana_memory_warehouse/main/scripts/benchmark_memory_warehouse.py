from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugin.store import CONTRACT_VERSION, MemoryWarehouseStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    event_count = max(1, min(args.events, 1_000_000))
    cases = json.loads((ROOT / "benchmarks" / "memory_quality_cases.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = MemoryWarehouseStore(tmp, max_content_chars=2000)
        store.initialize()
        started = perf_counter()
        for index in range(event_count):
            case = cases[index % len(cases)]
            result = store.ingest({
                "contract_version": CONTRACT_VERSION,
                "external_event_id": f"benchmark:{index}",
                "scope_id": case["scope_id"],
                "actor_id": case["actor_id"],
                "role": "user",
                "event_type": "benchmark",
                "content": f"{case['content']} #{index}",
                "metadata": {"case_id": case["id"]},
            })
            if not result.get("ok"):
                raise SystemExit(f"ingest_failed={result}")
        ingest_ms = round((perf_counter() - started) * 1000, 3)
        quality = []
        for case in cases:
            result = store.search(
                query=case["query"], scope_id=case["scope_id"],
                actor_id=case["actor_id"], limit=20,
            )
            cross_scope = any(
                item.get("scope_id") != case["scope_id"] or item.get("actor_id") != case["actor_id"]
                for item in result.get("results", [])
            )
            quality.append({"id": case["id"], "ok": result.get("ok") and not cross_scope, "count": result.get("count", 0)})
        rebuild_started = perf_counter()
        rebuild = store.rebuild_index()
        rebuild_ms = round((perf_counter() - rebuild_started) * 1000, 3)
        payload = {
            "ok": all(item["ok"] for item in quality) and rebuild.get("ok", False),
            "events": event_count,
            "ingest_ms": ingest_ms,
            "events_per_second": round(event_count / max(ingest_ms / 1000, 0.001), 2),
            "rebuild_ms": rebuild_ms,
            "database_bytes": store.db_path.stat().st_size,
            "quality": quality,
        }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8", newline="\n")
    print(serialized)
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
