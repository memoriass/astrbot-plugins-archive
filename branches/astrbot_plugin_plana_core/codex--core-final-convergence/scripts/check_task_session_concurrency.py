from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
from time import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.task_session import TaskSessionStore
from astrbot_plugin_plana_core.plugin.db import Database


SCOPE_ID = "scope:task-session-concurrency"
ACTOR_ID = "actor:test"


def require(condition: bool, message: object) -> None:
    if not condition:
        raise SystemExit(str(message))


def check_cross_store_claims(database: Database) -> None:
    for kind in ("confirm", "cancel", "retry"):
        stores = [
            TaskSessionStore(database, ttl_seconds=180),
            TaskSessionStore(database, ttl_seconds=180),
        ]
        barrier = Barrier(2)

        def claim(store: TaskSessionStore) -> str:
            barrier.wait()
            return store.claim_action(SCOPE_ID, ACTOR_ID, kind)

        with ThreadPoolExecutor(max_workers=2) as executor:
            tokens = list(executor.map(claim, stores))
        winners = [(store, token) for store, token in zip(stores, tokens) if token]
        require(len(winners) == 1, {"kind": kind, "tokens": tokens})
        require(winners[0][0].release_action(SCOPE_ID, ACTOR_ID, winners[0][1]), kind)


def check_revision_and_recovery(database: Database) -> None:
    first = TaskSessionStore(database, ttl_seconds=180)
    second = TaskSessionStore(database, ttl_seconds=180)
    first_state = first.session(SCOPE_ID, ACTOR_ID)
    first_state.latest_prompt = "original prompt"
    require(first.persist(first_state), "initial persist failed")

    stale_state = second.session(SCOPE_ID, ACTOR_ID)
    first_state.latest_failure = "new failure"
    first_state.updated_at = time()
    require(first.persist(first_state), "newer persist failed")
    stale_state.latest_prompt = "stale overwrite"
    stale_state.updated_at = time()
    require(not second.persist(stale_state), "stale revision unexpectedly won")

    restored = TaskSessionStore(database, ttl_seconds=180).session(SCOPE_ID, ACTOR_ID)
    require(restored.latest_failure == "new failure", restored.to_dict())
    require(restored.latest_prompt == "original prompt", restored.to_dict())

    token = first.claim_action(SCOPE_ID, ACTOR_ID, "retry")
    require(bool(token), "failed to create recovery claim")
    claimed = first.session(SCOPE_ID, ACTOR_ID)
    claimed.pending_action_started_at = time() - 181
    claimed.updated_at = time()
    require(first.persist(claimed), "failed to age recovery claim")
    recovered = TaskSessionStore(database, ttl_seconds=180)
    recovered_token = recovered.claim_action(SCOPE_ID, ACTOR_ID, "cancel")
    require(bool(recovered_token), "stale action claim blocked recovery")
    require(recovered.release_action(SCOPE_ID, ACTOR_ID, recovered_token), "release failed")


def check_payload_and_expiry_compatibility(database: Database) -> None:
    now = int(time())
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO assistant_conversation_frames(scope_id, actor_id, payload, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("scope:legacy", "actor:legacy", json.dumps({"latest_prompt": "legacy"}), now),
        )
        conn.execute(
            """
            INSERT INTO assistant_conversation_frames(scope_id, actor_id, payload, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("scope:expired", "actor:expired", "{}", now - 1000),
        )
    store = TaskSessionStore(database, ttl_seconds=180)
    legacy = store.session("scope:legacy", "actor:legacy")
    require(legacy.latest_prompt == "legacy" and legacy.revision == 0, legacy.to_dict())
    legacy.updated_at = time()
    require(store.persist(legacy), "legacy payload persist failed")
    with database.connect() as conn:
        primary_key = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(assistant_conversation_frames)")
            if int(row["pk"] or 0) > 0
        ]
        expired = conn.execute(
            """
            SELECT 1 FROM assistant_conversation_frames
            WHERE scope_id='scope:expired' AND actor_id='actor:expired'
            """
        ).fetchone()
    require(primary_key == ["scope_id", "actor_id"], primary_key)
    require(expired is None, "expired cleanup regressed")


def main() -> None:
    with TemporaryDirectory(prefix="plana-task-session-") as temporary:
        database = Database(Path(temporary) / "plana.sqlite3")
        check_cross_store_claims(database)
        check_revision_and_recovery(database)
        check_payload_and_expiry_compatibility(database)
    print("task session concurrency check passed")


if __name__ == "__main__":
    main()
