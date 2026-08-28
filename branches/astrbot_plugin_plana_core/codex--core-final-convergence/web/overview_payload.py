from __future__ import annotations

from typing import Any


def build_overview_payload(runtime: Any) -> dict[str, object]:
    debug = runtime.debug_status_payload()
    gallery = debug.get("gallery", {})
    return {
        "build": dict(getattr(runtime, "build_info", {})),
        "memory_production": {
            "memory_maintenance_last_run": getattr(
                runtime,
                "memory_maintenance_last_run",
                {},
            ),
        },
        "gallery": gallery if isinstance(gallery, dict) else {},
        "tables": runtime.storage.table_counts(),
    }
