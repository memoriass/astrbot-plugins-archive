from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.remote_task_store import RemoteTaskRunStore
from astrbot_plugin_plana_core.plugin.db import Database


def create_run(store: RemoteTaskRunStore, request_id: str) -> None:
    store.create(
        request_id=request_id,
        proactive_task_id=1,
        scope_id="scope",
        actor_id="actor",
        lane="interactive",
        title="test",
        payload={
            "request_id": request_id,
            "delivery_context": {
                "version": "plana.delivery.v1",
                "conversation_id": "origin",
                "source_message_id": f"message-{request_id}",
                "reply_to_message_id": f"message-{request_id}",
                "scope_id": "scope",
                "actor_id": "actor",
                "delivery_mode": "reply",
                "artifact_recipients": ["actor"],
                "fallback_mode": "mention_same_scope",
            },
        },
    )


def status(store: RemoteTaskRunStore, request_id: str) -> str:
    return next(item["status"] for item in store.recent(limit=20) if item["request_id"] == request_id)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="plana-remote-task-") as tmp:
        store = RemoteTaskRunStore(Database(Path(tmp) / "plana.sqlite3"))
        store.initialize()

        create_run(store, "v1-queued")
        stored_context = store.get("v1-queued")["delivery_context"]
        assert stored_context["source_message_id"] == "message-v1-queued"
        assert stored_context["actor_id"] == "actor"
        assert store.mark_submitted_if_nonterminal("v1-queued", runner_run_id="run-1")
        assert status(store, "v1-queued") == "submitted"

        for terminal in ("succeeded", "failed", "cancelled"):
            request_id = f"v2-{terminal}"
            create_run(store, request_id)
            assert store.update(request_id, status=terminal, result={"done": True})
            assert not store.mark_submitted_if_nonterminal(request_id, runner_run_id="late-deliver")
            assert status(store, request_id) == terminal

        create_run(store, "oversized-result")
        oversized = {
            "status": "succeeded",
            "request_id": "oversized-result",
            "result_summary": "subscription query complete",
            "error": "",
            "artifacts": [{"name": "report.json", "type": "json", "content": "x" * 20000}],
            "result": {
                "count": 100,
                "returned_count": 100,
                "subscriptions": [
                    {"id": index, "title": f"subscription-{index}", "details": "x" * 5000}
                    for index in range(100)
                ],
            },
        }
        assert store.update("oversized-result", status="succeeded", result=oversized)
        stored = next(item for item in store.recent(limit=20) if item["request_id"] == "oversized-result")
        assert stored["result"]["truncated"] is True
        assert stored["result"]["request_id"] == "oversized-result"
        assert stored["result"]["result"]["count"] == 100
        assert len(stored["result"]["result"]["subscriptions"]) <= 5
        with store.db.connect() as conn:
            raw_result = conn.execute(
                "SELECT result FROM remote_task_runs WHERE request_id=?",
                ("oversized-result",),
            ).fetchone()[0]
        assert len(raw_result) <= 16000
        assert isinstance(json.loads(raw_result), dict)

        with store.db.connect() as conn:
            conn.execute("DROP TABLE remote_task_runs")
            conn.execute(
                """
                CREATE TABLE remote_task_runs (
                    request_id TEXT PRIMARY KEY,
                    proactive_task_id INTEGER,
                    scope_id TEXT NOT NULL DEFAULT 'global',
                    actor_id TEXT NOT NULL DEFAULT '',
                    lane TEXT NOT NULL DEFAULT 'interactive',
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    payload TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    runner_run_id TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
        store.initialize()
        with store.db.connect() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(remote_task_runs)").fetchall()
            }
        assert "delivery_context" in columns

    print("remote task submission guard check passed")


if __name__ == "__main__":
    main()
