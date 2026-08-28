from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.remote_task_store import RemoteTaskRunStore
from astrbot_plugin_plana_core.plugin.db import Database


spec = importlib.util.spec_from_file_location(
    "plana_remote_task_payload",
    ROOT / "web" / "remote_task_payload.py",
)
if spec is None or spec.loader is None:
    raise RuntimeError("remote_task_payload_module_unavailable")
payload_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(payload_module)
build_remote_task_web_payload = payload_module.build_remote_task_web_payload


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="plana-remote-lifecycle-"))
    store = RemoteTaskRunStore(Database(root / "core.sqlite3"))
    store.initialize()
    store.create(
        request_id="codex-lifecycle",
        proactive_task_id=1,
        scope_id="scope:test",
        actor_id="actor:test",
        lane="interactive",
        title="lifecycle test",
        payload={"request_id": "codex-lifecycle"},
    )
    observation = {
        "attempt_id": "runner-1:attempt-1",
        "attempt_no": 1,
        "event_seq": 1,
        "heartbeat_at": 100,
        "lease_expires_at": 120,
    }
    assert store.apply_observation(
        "codex-lifecycle",
        status="running",
        runner_run_id="runner-1",
        observation=observation,
    ) == "applied"
    assert store.apply_observation(
        "codex-lifecycle",
        status="running",
        runner_run_id="runner-1",
        observation=observation,
    ) == "duplicate"
    current = store.get("codex-lifecycle")
    assert current and current["execution_state"]["event_seq"] == 1
    active = build_remote_task_web_payload({}, [current], now=110)["display_items"][0]
    assert active["display"]["connection_state"] == "connected"
    disconnected = build_remote_task_web_payload({}, [current], now=121)["display_items"][0]
    assert disconnected["display"]["connection_state"] == "disconnected"
    assert disconnected["display"]["status"] == "连接中断，等待恢复"
    assert store.apply_observation(
        "codex-lifecycle",
        status="cancelling",
        runner_run_id="runner-1",
        observation={**observation, "event_seq": 2, "cancel_acknowledged_at": 115},
    ) == "applied"
    cancelling = store.get("codex-lifecycle")
    assert cancelling and cancelling["execution_state"]["cancel_acknowledged_at"] == 115
    assert store.apply_terminal_result(
        "codex-lifecycle",
        status="cancelled",
        runner_run_id="runner-1",
        result={**observation, "event_seq": 3, "terminal_at": 116},
    ) == "applied"
    assert store.apply_observation(
        "codex-lifecycle",
        status="running",
        runner_run_id="runner-1",
        observation={**observation, "event_seq": 4},
    ) == "ignored_terminal"
    print("remote execution lifecycle check passed")


if __name__ == "__main__":
    main()
