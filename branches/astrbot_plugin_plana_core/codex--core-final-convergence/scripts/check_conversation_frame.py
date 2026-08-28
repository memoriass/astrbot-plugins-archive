from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.task_session import TaskRouteTrace, TaskSessionStore
from astrbot_plugin_plana_core.plugin.db import Database


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    with TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "plana.sqlite3")
        first = TaskSessionStore(database, ttl_seconds=180)
        first.record_trace(
            TaskRouteTrace(
                scope_id="group:test",
                actor_id="user:test",
                text="看一下 qB 当前有哪些下载任务",
                route="codex",
                capability="qbittorrent.list_torrents",
                expected_capability="qbittorrent.list_torrents",
                status="remote_queued",
            )
        )
        state = first.session("group:test", "user:test")
        state.latest_service_ref = "qbittorrent.production"
        state.latest_remote_request_id = "request-test"
        first.persist(state)

        restarted = TaskSessionStore(database, ttl_seconds=180)
        restored = restarted.session("group:test", "user:test")
        require(restored.latest_expected_capability == "qbittorrent.list_torrents", restored.to_dict())
        require(restored.latest_service_ref == "qbittorrent.production", restored.to_dict())
        require(restored.latest_remote_request_id == "request-test", restored.to_dict())
        require(restored.current_goal == "看一下 qB 当前有哪些下载任务", restored.to_dict())

    print("conversation_frame_check=ok")


if __name__ == "__main__":
    main()
