from __future__ import annotations

import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.remote_task import CodexDelegationRequest
from astrbot_plugin_plana_core.dialogue.remote_task_store import RemoteTaskRunStore
from astrbot_plugin_plana_core.dialogue.router import DialogueRouter
from astrbot_plugin_plana_core.dialogue.delivery import (
    remote_result_identity_error,
    reply_message_id_from_event,
    run_matches_reply,
)
from astrbot_plugin_plana_core.plugin.db import Database


class FakeRuntime:
    def resolve_scope(self, _origin: str) -> str:
        return "scope:group"


class FakeMessage:
    message_id = "message-100"


class FakeEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:100"
    message_obj = FakeMessage()
    is_wake = True
    is_at_or_wake_command = True

    def get_message_str(self) -> str:
        return "执行一个轻量任务"

    def get_message_type(self) -> str:
        return "GroupMessage"

    def get_sender_id(self) -> str:
        return "20001"

    def get_sender_name(self) -> str:
        return "Requester A"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_messages(self) -> list[object]:
        return []


class Reply:
    id = "message-100"


class FakeReplyEvent(FakeEvent):
    def get_messages(self) -> list[object]:
        return [Reply()]


def main() -> None:
    turn, _decision = DialogueRouter().decision_for_event(FakeRuntime(), FakeEvent())
    delivery = turn.delivery_context
    assert delivery["source_message_id"] == "message-100"
    assert delivery["reply_to_message_id"] == "message-100"
    assert delivery["scope_id"] == "scope:group"
    assert delivery["actor_id"] == "aiocqhttp:20001"

    payload = CodexDelegationRequest(
        text="task A",
        scope_id=turn.scope_id,
        actor_id=turn.actor_id,
        capability="test.read",
        reason="test",
        turn_context=turn.to_dict(),
    ).payload()
    assert payload["delivery_context"] == delivery

    with tempfile.TemporaryDirectory(prefix="plana-delivery-") as tmp:
        store = RemoteTaskRunStore(Database(Path(tmp) / "plana.sqlite3"))
        store.initialize()
        store.create(
            request_id=payload["request_id"],
            proactive_task_id=1,
            scope_id=turn.scope_id,
            actor_id=turn.actor_id,
            lane="interactive",
            title="task A",
            payload=payload,
        )
        run_a = store.get(payload["request_id"])
        assert run_a is not None
        assert run_a["delivery_context"]["source_message_id"] == "message-100"

        payload_b = {
            **payload,
            "request_id": "request-b",
            "actor_id": "aiocqhttp:20002",
            "delivery_context": {
                **delivery,
                "actor_id": "aiocqhttp:20002",
                "actor_display_name": "Requester B",
                "source_message_id": "message-200",
                "reply_to_message_id": "message-200",
                "artifact_recipients": ["aiocqhttp:20002"],
            },
        }
        store.create(
            request_id="request-b",
            proactive_task_id=2,
            scope_id=turn.scope_id,
            actor_id="aiocqhttp:20002",
            lane="interactive",
            title="task B",
            payload=payload_b,
        )
        run_b = store.get("request-b")
        assert run_b is not None
        assert run_a["delivery_context"]["actor_id"] != run_b["delivery_context"]["actor_id"]
        assert run_a["delivery_context"]["reply_to_message_id"] != run_b["delivery_context"]["reply_to_message_id"]
        reply_message_id = reply_message_id_from_event(FakeReplyEvent())
        assert reply_message_id == "message-100"
        assert run_matches_reply(run_a, reply_message_id)
        assert not run_matches_reply(run_b, reply_message_id)

        assert not remote_result_identity_error(
            run_a,
            scope_id="scope:group",
            actor_id="aiocqhttp:20001",
        )
        assert remote_result_identity_error(
            run_a,
            scope_id="scope:other",
            actor_id="aiocqhttp:20001",
        ) == "remote_result_scope_mismatch"
        assert remote_result_identity_error(
            run_a,
            scope_id="scope:group",
            actor_id="aiocqhttp:20002",
        ) == "remote_result_actor_mismatch"

    print("delivery context check passed")


if __name__ == "__main__":
    main()
