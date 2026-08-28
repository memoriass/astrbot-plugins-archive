from __future__ import annotations

import sys
import types


class FakeRuntime:
    def __init__(self) -> None:
        self.enabled = True
        self.config = {
            "enable_dialogue_wake_state": True,
            "dialogue_wake_words": "plana",
            "dialogue_familiar_window_seconds": 180,
            "dialogue_observation_window_seconds": 90,
            "dialogue_poke_response": "Poke reply",
            "dialogue_response_preflight_enabled": True,
            "dialogue_response_preflight_timeout_seconds": 0.2,
        }
        self.remembered: list[str] = []

    def resolve_scope(self, _origin: str) -> str:
        return "scope"

    def ingest_event(self, _event) -> None:
        return None

    def record_response(self, _event, _text: str) -> None:
        return None

    def status_text(self) -> str:
        return "Plana status: ok"

    def user_status_text(self) -> str:
        return "I am online. Use /plana status for diagnostics."

    def remember_text(self, _event, content: str) -> str:
        self.remembered.append(content)
        return "Plana remember: stored"

    def search_text(self, _event, query: str) -> str:
        return f"Plana memory search: {query or '<recent>'}\n1. deployment notes"

    async def extract_and_index_concepts(self, _text: str, _provider) -> None:
        return None

    async def extract_structured_memories(self, _event, _text: str, _provider) -> None:
        return None

    async def update_mood_by_response(self, _text: str, _provider) -> None:
        return None

class FakePolicy:
    async def build_prompt_block(self, runtime, event, provider, **_kwargs) -> str:
        return "base prompt context"


class FakeRequest:
    system_prompt = "system"


class FakeRequestWithParts:
    def __init__(self) -> None:
        self.system_prompt = "system"
        self.extra_user_content_parts: list[object] = []


class FakeTextPart:
    def __init__(self, text: str) -> None:
        self.text = text

    def mark_as_temp(self):
        self._no_save = True
        return self


class FakeTextPartWithoutTemp:
    def __init__(self, text: str) -> None:
        self.text = text


def install_fake_text_part() -> None:
    sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    sys.modules.setdefault("astrbot.core.agent", types.ModuleType("astrbot.core.agent"))
    message = types.ModuleType("astrbot.core.agent.message")
    message.TextPart = FakeTextPart
    sys.modules["astrbot.core.agent.message"] = message


def install_fake_text_part_without_temp() -> None:
    sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
    sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
    sys.modules.setdefault("astrbot.core.agent", types.ModuleType("astrbot.core.agent"))
    message = types.ModuleType("astrbot.core.agent.message")
    message.TextPart = FakeTextPartWithoutTemp
    sys.modules["astrbot.core.agent.message"] = message


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.completion_text = text


class FakeEvent:
    unified_msg_origin = "platform:FriendMessage:user"
    is_wake = False
    is_at_or_wake_command = False
    call_llm = False

    def __init__(
        self,
        text: str,
        *,
        private: bool = True,
        wake: bool = False,
        at: bool = False,
        message_type: str = "",
        platform: str = "test",
    ) -> None:
        self.text = text
        self.private = private
        self.is_wake = wake
        self.is_at_or_wake_command = at
        self.message_type = message_type
        self.platform = platform

    def get_message_str(self) -> str:
        return self.text

    def get_message_type(self) -> str:
        if self.message_type:
            return self.message_type
        return "FriendMessage" if self.private else "GroupMessage"

    def get_sender_id(self) -> str:
        return "tester"

    def get_sender_name(self) -> str:
        return "Tester"

    def is_private_chat(self) -> bool:
        return self.private

    def get_platform_name(self) -> str:
        return self.platform

    def get_platform_id(self) -> str:
        return self.platform


class FakePlugin:
    _terminating = False

    def __init__(self) -> None:
        self.runtime = FakeRuntime()
        self.dialogue = self
        self.observed: list[str] = []
        self.scheduled: list[str] = []

    def observe_message(self, event) -> None:
        self.observed.append(event.get_message_str())

    def _schedule_passive_dialogue_observe(self, event) -> None:
        self.scheduled.append(event.get_message_str())
        self.observe_message(event)
