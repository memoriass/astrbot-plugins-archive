from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT.parent
sys.path.insert(0, str(PACKAGE_ROOT))

root_package = types.ModuleType("astrbot_plugin_plana_core")
root_package.__path__ = [str(ROOT)]
dialogue_package = types.ModuleType("astrbot_plugin_plana_core.dialogue")
dialogue_package.__path__ = [str(ROOT / "dialogue")]
plugin_package = types.ModuleType("astrbot_plugin_plana_core.plugin")
plugin_package.__path__ = [str(ROOT / "plugin")]
sys.modules.setdefault("astrbot_plugin_plana_core", root_package)
sys.modules.setdefault("astrbot_plugin_plana_core.dialogue", dialogue_package)
sys.modules.setdefault("astrbot_plugin_plana_core.plugin", plugin_package)

from astrbot_plugin_plana_core.dialogue.message_anchor import (  # noqa: E402
    MessageAnchor,
    MessageAnchorStore,
    register_sent_message_anchors,
)
from astrbot_plugin_plana_core.plugin.db import Database  # noqa: E402


@dataclass
class FakeIdentity:
    global_user_id: str


class FakeRuntime:
    def resolve_scope(self, _origin: str) -> str:
        return "scope:group"

    def identity_from_event(self, event: object) -> FakeIdentity:
        return FakeIdentity(f"qq:{event.get_sender_id()}")


@dataclass
class FakeBehavior:
    action: str = "codex"
    capability: str = "filesystem.read"
    risk_class: str = "confirmation_required"
    media_intent: str = "text"
    delivery_context: dict[str, object] | None = None


@dataclass
class FakeState:
    latest_prompt: str
    latest_pending_run_id: int | None = None
    latest_remote_request_id: str = ""


class FakeSessionStore:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    def session(self, _scope_id: str, _actor_id: str) -> FakeState:
        return self.state


class FakeMessage:
    def __init__(self, message_id: str) -> None:
        self.message_id = message_id


class Reply:
    def __init__(self, message_id: str) -> None:
        self.id = message_id


class FakeEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:100"
    _plana_anchor_outbound = True
    _plana_behavior_decision = FakeBehavior(delivery_context={})

    def __init__(
        self,
        *,
        sender_id: str,
        source_message_id: str,
        sent_ids: object = None,
        reply_id: str = "",
        text: str = "执行任务",
    ) -> None:
        self.sender_id = sender_id
        self.message_obj = FakeMessage(source_message_id)
        self.text = text
        self.messages = [Reply(reply_id)] if reply_id else []
        self.extras = {}
        self.sent_ids = sent_ids
        self.extras["_plana_public_projection"] = {
            "status": "waiting_confirm",
            "kind": "mikan_groups",
            "count": 2,
            "items": [
                {"id": "group-1", "name": "安全字幕组"},
                {"id": "group-2", "name": "https://must-not-leak.example"},
            ],
            "task_id": "must-not-leak",
            "private_payload": "must-not-leak",
        }

    def get_extra(self, key: str, default=None):
        return self.extras.get(key, default)

    def get_sent_message_ids(self):
        return self.sent_ids if self.sent_ids is not None else ()

    def get_sender_id(self) -> str:
        return self.sender_id

    def get_message_str(self) -> str:
        return self.text

    def get_messages(self) -> list[object]:
        return self.messages


def row_count(database: Database) -> int:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM assistant_message_anchors"
        ).fetchone()
    return int(row[0])


def main() -> None:
    runtime = FakeRuntime()
    state = FakeState("执行任务", latest_pending_run_id=42)
    sessions = FakeSessionStore(state)
    with tempfile.TemporaryDirectory(prefix="plana-message-anchor-") as tmp:
        database = Database(Path(tmp) / "plana.sqlite3")
        store = MessageAnchorStore(database)
        store.initialize()

        missing = FakeEvent(
            sender_id="1001",
            source_message_id="incoming-missing",
        )
        assert register_sent_message_anchors(
            missing, runtime=runtime, store=store, session_store=sessions
        ) == 0
        assert row_count(database) == 0

        first = FakeEvent(
            sender_id="1001",
            source_message_id="incoming-1",
            sent_ids=["bot-1", {"message_id": "bot-2"}, "bot-1"],
        )
        assert register_sent_message_anchors(
            first,
            runtime=runtime,
            store=store,
            session_store=sessions,
            ttl_seconds=300,
            now=1000,
        ) == 2
        assert row_count(database) == 2

        owner = store.resolve_reply("scope:group", "bot-1", "qq:1001", now=1001)
        assert owner is not None
        assert owner.is_owner and owner.task_id == "42"
        assert owner.root_message_id == "incoming-1"
        assert owner.source_message_id == "incoming-1"
        assert owner.can_inherit_task and owner.can_confirm
        assert owner.public_projection["status"] == "waiting_confirm"
        assert owner.public_projection["kind"] == "mikan_groups"
        assert owner.public_projection["items"] == [
            {"id": "group-1", "name": "安全字幕组"},
            {"id": "group-2"},
        ]
        assert "task_id" not in owner.public_projection
        assert "private_payload" not in owner.public_projection

        foreign = store.resolve_reply("scope:group", "bot-1", "qq:2002", now=1001)
        assert foreign is not None and not foreign.is_owner
        assert not foreign.owner_actor_id and not foreign.task_id
        assert not foreign.root_message_id and not foreign.source_message_id
        assert not foreign.can_inherit_task and not foreign.can_confirm
        assert foreign.public_projection == owner.public_projection

        assert register_sent_message_anchors(
            first,
            runtime=runtime,
            store=store,
            session_store=sessions,
            ttl_seconds=600,
            now=1010,
        ) == 2
        assert row_count(database) == 2

        state.latest_prompt = "different turn"
        continued = FakeEvent(
            sender_id="1001",
            source_message_id="incoming-2",
            sent_ids="bot-3",
            reply_id="bot-1",
            text="继续",
        )
        assert register_sent_message_anchors(
            continued, runtime=runtime, store=store, session_store=sessions, now=1020
        ) == 1
        inherited = store.resolve_reply("scope:group", "bot-3", "qq:1001", now=1021)
        assert inherited is not None
        assert inherited.task_id == "42"
        assert inherited.root_message_id == "incoming-1"

        forked = FakeEvent(
            sender_id="2002",
            source_message_id="incoming-3",
            sent_ids="bot-4",
            reply_id="bot-1",
            text="我也看看",
        )
        assert register_sent_message_anchors(
            forked, runtime=runtime, store=store, session_store=sessions, now=1030
        ) == 1
        fork = store.resolve_reply("scope:group", "bot-4", "qq:2002", now=1031)
        assert fork is not None
        assert not fork.task_id
        assert fork.root_message_id == "incoming-3"
        assert not fork.can_confirm

        store.register(
            MessageAnchor(
                "scope:group", "expired", "qq:1001", "9", "root", "source",
                "pending_confirmation", {}, 1, 1, 2,
            )
        )
        assert store.resolve_reply("scope:group", "expired", "qq:1001", now=3) is None

    plugin_events = (ROOT / "plugin" / "plugin_events.py").read_text(encoding="utf-8")
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "await super()._handle_after_message_sent(event)" in plugin_events
    assert "@filter.after_message_sent" in main_source
    print("message anchor check passed")


if __name__ == "__main__":
    main()
