from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
ASTRBOT_ROOT = ROOT.parent / "AstrBot"
if ASTRBOT_ROOT.is_dir():
    sys.path.insert(0, str(ASTRBOT_ROOT))

from astrbot_plugin_plana_core.dialogue.message_anchor import (  # noqa: E402
    MessageAnchor,
    MessageAnchorStore,
)
from astrbot_plugin_plana_core.dialogue.service_support import (  # noqa: E402
    DialogueServiceSupportMixin,
)
from astrbot_plugin_plana_core.dialogue.task_session import (  # noqa: E402
    TaskSessionStore,
)
from astrbot_plugin_plana_core.dialogue.wake import (  # noqa: E402
    DialogueWakeStateMachine,
)
from astrbot_plugin_plana_core.plugin.db import Database  # noqa: E402


@dataclass
class Identity:
    global_user_id: str


class Reply:
    def __init__(self, message_id: str) -> None:
        self.id = message_id


class Event:
    unified_msg_origin = "group:100"
    message_type = "GroupMessage"

    def __init__(self, actor_id: str, text: str, reply_id: str = "") -> None:
        self.actor_id = actor_id
        self.text = text
        self.messages = [Reply(reply_id)] if reply_id else []

    def get_message_str(self) -> str:
        return self.text

    def get_message_type(self) -> str:
        return self.message_type

    def get_sender_id(self) -> str:
        return self.actor_id

    def get_messages(self) -> list[Reply]:
        return self.messages

    def is_private_chat(self) -> bool:
        return False


class Runtime:
    def __init__(self, store: MessageAnchorStore) -> None:
        self.config = {
            "enable_dialogue_wake_state": True,
            "dialogue_familiar_window_seconds": 180,
            "dialogue_observation_window_seconds": 90,
        }
        self.storage = SimpleNamespace(message_anchors=store)

    def resolve_scope(self, origin: str) -> str:
        return origin

    def identity_from_event(self, event: Event) -> Identity:
        return Identity(f"qq:{event.actor_id}")


class Service(DialogueServiceSupportMixin):
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.wake_state = DialogueWakeStateMachine()
        self.task_broker = SimpleNamespace(sessions=TaskSessionStore())


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="plana-group-isolation-") as tmp:
        database = Database(Path(tmp) / "plana.sqlite3")
        anchors = MessageAnchorStore(database)
        anchors.initialize()
        anchors.register(
            MessageAnchor(
                scope_id="group:100",
                message_id="bot-result-1",
                owner_actor_id="qq:1001",
                task_id="private-task-id",
                root_message_id="source-1",
                source_message_id="source-1",
                anchor_kind="service_query_result",
                public_projection={
                    "capability": "ani_rss.list_mikan_groups",
                    "kind": "mikan_groups",
                    "count": 2,
                    "items": [
                        {"id": "group-1", "name": "字幕组 A"},
                        {"id": "group-2", "name": "字幕组 B"},
                    ],
                },
                created_at=1000,
                updated_at=1000,
                expires_at=4_102_444_800,
            )
        )

        service = Service(Runtime(anchors))
        owner_state = service.task_broker.sessions.session("group:100", "qq:1001")
        owner_state.current_goal = "查询尼古喵喵字幕组"
        owner_state.latest_prompt = "有哪些字幕组"

        owner_event = Event("1001", "换一个字幕组", "bot-result-1")
        owner_decision = service._wake_decision(owner_event)
        assert owner_decision.should_dispatch
        assert owner_decision.reason == "anchored_owner_reply"
        owner_resolution = owner_event._plana_message_anchor_resolution
        assert owner_resolution.can_inherit_task
        assert owner_resolution.task_id == "private-task-id"

        foreign_event = Event("2002", "我也看看", "bot-result-1")
        foreign_decision = service._wake_decision(foreign_event)
        assert foreign_decision.should_dispatch
        assert foreign_decision.reason == "anchored_public_fork"
        foreign_resolution = foreign_event._plana_message_anchor_resolution
        assert not foreign_resolution.can_inherit_task
        assert not foreign_resolution.can_confirm
        assert foreign_resolution.task_id == ""
        prompt = service._message_anchor_prompt(foreign_event)
        assert "read-only branch" in prompt
        assert "private-task-id" not in prompt
        assert "字幕组 A" in prompt

        unrelated_foreign = Event("2002", "换一个")
        assert not service._wake_decision(unrelated_foreign).should_dispatch

        service.wake_state.observe_response(service.runtime, owner_event)
        unrelated_owner = Event("1001", "哈哈哈")
        assert not service._wake_decision(unrelated_owner).should_dispatch

    print("group_session_isolation_check=ok")


if __name__ == "__main__":
    main()
