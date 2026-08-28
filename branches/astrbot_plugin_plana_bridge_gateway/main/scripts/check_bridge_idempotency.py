from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "bridge_idempotency_under_test", ROOT / "bridge" / "idempotency.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
DeliveryIdempotencyLedger = module.DeliveryIdempotencyLedger


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        ledger = DeliveryIdempotencyLedger(Path(tmp) / "ledger.sqlite3")
        ledger.initialize()
        payload = {"request_id": "req-1", "run_id": "run-1", "status": "succeeded"}
        poll = ledger.record_phase("idem-1", "poll", "succeeded", payload)
        replay = ledger.record_phase("idem-1", "poll", "succeeded", payload)
        conflict = ledger.record_phase(
            "idem-1", "poll", "failed", {**payload, "status": "failed"}
        )
        callback = ledger.record_phase("idem-1", "callback", "succeeded", payload)
        artifact = ledger.record_phase(
            "idem-1", "artifact", "succeeded", {**payload, "artifacts": [{"sha256": "abc"}]}
        )
        terminal = ledger.record_terminal("idem-1", "succeeded", payload)
        terminal_replay = ledger.record_terminal("idem-1", "succeeded", payload)
        terminal_conflict = ledger.record_terminal(
            "idem-1", "failed", {**payload, "status": "failed"}
        )
        assert poll["ok"] and replay["replay"] and conflict["conflict"]
        assert callback["ok"] and artifact["ok"]
        assert terminal["ok"] and terminal_replay["replay"] and terminal_conflict["conflict"]
        assert {item["phase"] for item in ledger.phases("idem-1")} == {"poll", "callback", "artifact"}
    print("bridge_idempotency_check=ok")


if __name__ == "__main__":
    main()
