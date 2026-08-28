from __future__ import annotations

import io
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.path.insert(0, str(ROOT.parent))
    from astrbot_plugin_plana_core.memory.warehouse_client import MemoryWarehouseClient

    original = urllib.request.urlopen

    def unavailable(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://127.0.0.1", 503, "down", None,
            io.BytesIO(b'{"error":"unavailable"}'),
        )

    urllib.request.urlopen = unavailable
    try:
        client = MemoryWarehouseClient({"plana_core_service_key": "test-key"})
        result = client.ingest(content="http only", scope_id="scope")
    finally:
        urllib.request.urlopen = original
    assert result["ok"] is False, result
    assert result["error"] == "unavailable", result
    assert client.local_status()["last_transport"] == "loopback_http"
    source = (ROOT / "memory" / "warehouse_client.py").read_text(encoding="utf-8")
    assert "MemoryWarehouseStore" not in source
    assert "direct_fallback" not in source
    print("memory_warehouse_http_only_check=ok")


if __name__ == "__main__":
    main()
