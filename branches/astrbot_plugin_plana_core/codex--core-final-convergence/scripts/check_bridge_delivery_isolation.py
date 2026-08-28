from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


class FakeMessageChain:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def message(self, text: str):
        self.parts.append(text)
        return self

    def file_image(self, path: str):
        self.parts.append(f"[image]{path}")
        return self

    def get_plain_text(self) -> str:
        return " ".join(self.parts)


astrbot_module = types.ModuleType("astrbot")
astrbot_api_module = types.ModuleType("astrbot.api")
astrbot_event_module = types.ModuleType("astrbot.api.event")
astrbot_event_module.MessageChain = FakeMessageChain
sys.modules.setdefault("astrbot", astrbot_module)
sys.modules.setdefault("astrbot.api", astrbot_api_module)
sys.modules.setdefault("astrbot.api.event", astrbot_event_module)

quart_module = types.ModuleType("quart")
quart_module.jsonify = lambda value: value
quart_module.request = object()
sys.modules.setdefault("quart", quart_module)

renderer_module = types.ModuleType(
    "astrbot_plugin_plana_core.presentation.result_renderer"
)


async def fake_render_to_file(_document: dict) -> str:
    return "unused.png"


renderer_module._render_to_file = fake_render_to_file
sys.modules.setdefault(
    "astrbot_plugin_plana_core.presentation.result_renderer", renderer_module
)

dialogue_package = types.ModuleType("astrbot_plugin_plana_core.dialogue")
dialogue_package.__path__ = [str(ROOT / "dialogue")]
plugin_package = types.ModuleType("astrbot_plugin_plana_core.plugin")
plugin_package.__path__ = [str(ROOT / "plugin")]
sys.modules.setdefault("astrbot_plugin_plana_core.dialogue", dialogue_package)
sys.modules.setdefault("astrbot_plugin_plana_core.plugin", plugin_package)

memory_module = types.ModuleType("astrbot_plugin_plana_core.memory")
memory_module.ALL_MEMORY_KINDS = frozenset()
memory_module.MEMORY_KIND_BRIDGE_HANDOFF = "bridge_handoff"
sys.modules.setdefault("astrbot_plugin_plana_core.memory", memory_module)

web_package = types.ModuleType("astrbot_plugin_plana_core.web")
web_package.__path__ = [str(ROOT / "web")]
web_auth_module = types.ModuleType("astrbot_plugin_plana_core.web.auth")
web_auth_module.is_loopback_request = lambda _request: True
sys.modules.setdefault("astrbot_plugin_plana_core.web", web_package)
sys.modules.setdefault("astrbot_plugin_plana_core.web.auth", web_auth_module)

from astrbot_plugin_plana_core.plugin.plugin_bridge import PlanaPluginBridgeMixin


class FakeContext:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, scope_id: str, chain) -> bool:
        self.sent.append((scope_id, chain.get_plain_text()))
        return True


class FakeSessionService:
    @staticmethod
    def _remote_success_reply(run: dict) -> str:
        return str(run["result"].get("result_summary") or "完成")

    @staticmethod
    def _remote_render_document(_run: dict):
        return None


class FakeBroker:
    session_service = FakeSessionService()


class FakeDialogue:
    task_broker = FakeBroker()


class BridgeHarness(PlanaPluginBridgeMixin):
    def __init__(self) -> None:
        self.context = FakeContext()
        self.dialogue = FakeDialogue()


async def main() -> None:
    bridge = BridgeHarness()
    first = {
        "scope_id": "scope:a",
        "delivery_context": {
            "conversation_id": "webchat:FriendMessage:webchat!admin!session-a",
            "delivery_policy": "reply_then_mention",
        },
    }
    second = {
        "scope_id": "scope:b",
        "delivery_context": {
            "conversation_id": "aiocqhttp:GroupMessage:20002",
            "delivery_policy": "reply_then_mention",
        },
    }
    results = await asyncio.gather(
        bridge._deliver_bridge_result(first, {"result_summary": "结果 A"}),
        bridge._deliver_bridge_result(second, {"result_summary": "结果 B"}),
    )
    assert results == [True, True]
    assert bridge.context.sent == [
        ("webchat:FriendMessage:webchat!admin!session-a", "结果 A"),
        ("aiocqhttp:GroupMessage:20002", "结果 B"),
    ]

    private_only = {
        "scope_id": "aiocqhttp:GroupMessage:20002",
        "delivery_context": {
            "conversation_id": "aiocqhttp:GroupMessage:20002",
            "delivery_policy": "private_only",
            "artifact_recipients": ["aiocqhttp:FriendMessage:30003"],
        },
    }
    assert await bridge._deliver_bridge_result(
        private_only, {"result_summary": "私发二维码"}
    )
    assert bridge.context.sent[-1] == (
        "aiocqhttp:FriendMessage:30003",
        "私发二维码",
    )

    undeliverable = {
        "scope_id": "aiocqhttp:GroupMessage:20002",
        "delivery_context": {
            "conversation_id": "aiocqhttp:GroupMessage:20002",
            "delivery_policy": "private_only",
            "artifact_recipients": ["actor-only"],
        },
    }
    before = list(bridge.context.sent)
    assert not await bridge._deliver_bridge_result(
        undeliverable, {"result_summary": "不能发到群里"}
    )
    assert bridge.context.sent == before

    internal_scope = {
        "scope_id": "validation:production-governance",
        "delivery_context": {
            "conversation_id": "validation:production-governance",
            "delivery_policy": "reply_then_mention",
        },
    }
    assert not await bridge._deliver_bridge_result(
        internal_scope, {"result_summary": "仅记录，不外发"}
    )
    assert bridge.context.sent == before
    print("bridge delivery isolation check passed")


if __name__ == "__main__":
    asyncio.run(main())
