from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from time import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.continuation import assess_group_continuation
from astrbot_plugin_plana_core.dialogue.domain_tool_route import (
    is_domain_followup_text,
    normalize_domain_tool_arguments,
)
from astrbot_plugin_plana_core.dialogue.domain_contracts import (
    DOMAIN_PLUGINS,
    DomainPluginDescriptor,
)
from astrbot_plugin_plana_core.dialogue.task_session import TaskSessionState
from astrbot_plugin_plana_core.dialogue.wake import DialogueWakeStateMachine


@dataclass
class _Identity:
    global_user_id: str


class _Runtime:
    def __init__(self) -> None:
        self.config = {
            "enable_dialogue_wake_state": True,
            "dialogue_familiar_window_seconds": 180,
            "dialogue_observation_window_seconds": 90,
        }

    def resolve_scope(self, origin: str) -> str:
        return origin

    def identity_from_event(self, event: "_Event") -> _Identity:
        return _Identity(f"qq:{event.actor_id}")


class Reply:
    def __init__(self, message_id: str = "message-1") -> None:
        self.id = message_id


@dataclass
class _Anchor:
    is_owner: bool
    public_projection: dict[str, object] = field(default_factory=dict)


@dataclass
class _Event:
    text: str
    actor_id: str = "10001"
    private: bool = False
    reply: bool = False
    unified_msg_origin: str = "group:test"
    is_wake: bool = False
    is_at_or_wake_command: bool = False
    call_llm: bool = False
    message_type: str = field(init=False)

    def __post_init__(self) -> None:
        self.message_type = "FriendMessage" if self.private else "GroupMessage"

    def get_message_str(self) -> str:
        return self.text

    def get_message_type(self) -> str:
        return self.message_type

    def get_sender_id(self) -> str:
        return self.actor_id

    def is_private_chat(self) -> bool:
        return self.private

    def get_messages(self) -> list[Reply]:
        return [Reply()] if self.reply else []


def _state(actor_id: str = "qq:10001", *, recent: bool = True) -> TaskSessionState:
    return TaskSessionState(
        scope_id="group:test",
        actor_id=actor_id,
        current_goal="\u68c0\u67e5\u4e0b\u8f7d\u4efb\u52a1",
        latest_prompt="\u68c0\u67e5\u4e0b\u8f7d\u4efb\u52a1",
        latest_route="codex_candidate",
        updated_at=time() if recent else time() - 600,
    )


def _assert_service_cache_usage() -> None:
    service = (ROOT / "dialogue" / "service.py").read_text(encoding="utf-8")
    support = (ROOT / "dialogue" / "service_support.py").read_text(encoding="utf-8")
    assert service.count("self._wake_decision(event)") == 3
    assert "self.wake_state.decide(self.runtime, event)" not in service
    assert "wake = self._wake_decision(event)" in support
    plugin_events = (ROOT / "plugin" / "plugin_events.py").read_text(encoding="utf-8")
    domain_routing = (ROOT / "plugin" / "domain_routing.py").read_text(encoding="utf-8")
    assert "self.dialogue.wake_state.observe_response" in plugin_events
    assert "_resume_recent_tool_profile" in domain_routing
    prepare_turn = plugin_events.split("def _prepare_native_turn", 1)[1].split(
        "def _execute_native_search_turn", 1
    )[0]
    assert prepare_turn.index("tool_profile_for_text") < prepare_turn.index(
        "_resume_recent_tool_profile"
    )
    assert "if current_profile in DOMAIN_TOOL_PROFILES:" in prepare_turn
    assert '"has_pending_task_action"' in prepare_turn
    assert "callable(pending_action_check)" in prepare_turn
    assert "elif not pending_task_action and not discussion and self._resume_recent_tool_profile" in prepare_turn
    assert "self._remember_recent_tool_profile(event)" not in prepare_turn
    assert "_execute_domain_turn" in domain_routing
    assert "前文请求：{context_text}" in domain_routing
    direct_dispatch = domain_routing.split("async def _execute_domain_turn", 1)[1].split(
        "def _remember_recent_tool_profile", 1
    )[0]
    assert direct_dispatch.index("_handle_using_llm_tool") < direct_dispatch.index(
        "tool_args.update("
    )
    assert "_plana_domain_profile_committed" in domain_routing
    assert "跟进补充：" in domain_routing
    assert "_plana_domain_handler_executed" in plugin_events
    assert "resume(event, text)" in (ROOT / "dialogue" / "entry_filters.py").read_text(encoding="utf-8")
    assert "session_state=session_state" in support


def main() -> int:
    DOMAIN_PLUGINS.replace(
        [
            DomainPluginDescriptor(
                schema_version=1,
                domain_id="ncqq",
                owner="test",
                profile="ncqq_plugin",
                tool_name="ncqq_manager",
                direct_dispatch=True,
            )
        ]
    )
    runtime = _Runtime()
    wake = DialogueWakeStateMachine()

    actor_a_wake = _Event(
        "plana help",
        actor_id="10001",
        is_wake=True,
        is_at_or_wake_command=True,
    )
    assert wake.decide(runtime, actor_a_wake, session_state=_state()).should_dispatch
    wake.observe_response(runtime, actor_a_wake)

    unrelated_a = _Event("\u4eca\u5929\u5929\u6c14\u4e0d\u9519", actor_id="10001")
    unrelated_decision = wake.decide(runtime, unrelated_a, session_state=_state())
    assert unrelated_decision.state == "observation"
    assert not unrelated_decision.should_dispatch

    continuation_a = _Event("\u90a3\u7ee7\u7eed\u5427", actor_id="10001")
    continuation_decision = wake.decide(runtime, continuation_a, session_state=_state())
    assert continuation_decision.should_dispatch

    natural_pronoun = _Event("那刚才那个起来了吗", actor_id="10001")
    natural_pronoun_decision = wake.decide(
        runtime, natural_pronoun, session_state=_state()
    )
    assert natural_pronoun_decision.should_dispatch
    assert is_domain_followup_text("那刚才那个起来了吗")
    assert is_domain_followup_text("那刚才那个再帮我查一下")
    assert is_domain_followup_text("那就帮我处理一下，弄好把码发我")
    assert is_domain_followup_text("确认，就删这个，数据一起清掉")
    assert is_domain_followup_text("算了，先取消")
    assert not is_domain_followup_text("确认一下这个技术方案是否合理")
    tool_args = {"workflow": "check_instance", "target": "compressed", "params": ""}
    assert normalize_domain_tool_arguments(
        "ncqq_plugin",
        "ncqq_manager",
        "确认，就按这个来",
        tool_args,
    )
    assert tool_args == {
        "workflow": "ai_dispatch",
        "target": "确认，就按这个来",
        "params": {},
    }

    actor_b = _Event("\u90a3\u7ee7\u7eed\u5427", actor_id="10002")
    assert not wake.decide(
        runtime,
        actor_b,
        session_state=_state("qq:10002"),
    ).should_dispatch

    unanchored_reply = assess_group_continuation(
        _Event("not for plana", reply=True),
        TaskSessionState(scope_id="group:test", actor_id="qq:10001"),
    )
    assert unanchored_reply.reply_signal
    assert not unanchored_reply.should_continue

    stale_reply = assess_group_continuation(
        _Event("not for plana", reply=True),
        _state(recent=False),
    )
    assert not stale_reply.should_continue
    recent_reply = assess_group_continuation(
        _Event("not for plana", reply=True),
        _state(),
        scope_id="group:test",
        actor_id="qq:10001",
    )
    assert recent_reply.should_continue
    assert recent_reply.reason == "recent_task_reply_signal"
    wrong_actor_reply = assess_group_continuation(
        _Event("not for plana", actor_id="10002", reply=True),
        _state(),
        scope_id="group:test",
        actor_id="qq:10002",
    )
    assert not wrong_actor_reply.should_continue

    owner_anchor = _Anchor(True, {"kind": "mikan_groups"})
    anchored_owner_event = _Event("换一个字幕组", reply=True)
    anchored_owner = wake.decide(
        runtime,
        anchored_owner_event,
        session_state=_state(),
        anchor_resolution=owner_anchor,
    )
    assert anchored_owner.should_dispatch
    assert anchored_owner.reason == "anchored_owner_reply"

    public_anchor = _Anchor(False, {"kind": "mikan_groups"})
    anchored_foreign_event = _Event("我也看看", actor_id="10002", reply=True)
    anchored_foreign = wake.decide(
        runtime,
        anchored_foreign_event,
        session_state=TaskSessionState(
            scope_id="group:test",
            actor_id="qq:10002",
        ),
        anchor_resolution=public_anchor,
    )
    assert anchored_foreign.should_dispatch
    assert anchored_foreign.reason == "anchored_public_fork"

    cached_event = _Event("\u90a3\u7ee7\u7eed\u5427")
    first = wake.decide(runtime, cached_event, session_state=_state())
    second = wake.decide(runtime, cached_event, session_state=None)
    assert first is second

    private_wake = _Event("hello", private=True, unified_msg_origin="friend:10001")
    private_decision = wake.decide(runtime, private_wake)
    assert private_decision.source == "private_chat"
    assert private_decision.should_dispatch

    _assert_service_cache_usage()
    print("group continuation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
