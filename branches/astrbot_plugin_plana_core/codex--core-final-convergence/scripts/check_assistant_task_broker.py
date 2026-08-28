from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.domain_contracts import (  # noqa: E402
    DOMAIN_PLUGINS,
    DomainPluginDescriptor,
)
from astrbot_plugin_plana_core.dialogue.task_broker import AssistantTaskRouter  # noqa: E402
from astrbot_plugin_plana_core.dialogue.task_broker_models import (  # noqa: E402
    AssistantTaskRequest,
)


class Event:
    unified_msg_origin = "aiocqhttp:GroupMessage:acceptance"

    def get_sender_id(self) -> str:
        return "tester"


class Runtime:
    def __init__(self) -> None:
        self.config = {
            "assistant_task_enabled": True,
            "assistant_native_tool_mode": True,
            "assistant_low_risk_autorun": True,
            "assistant_remote_runner_enabled": True,
        }
        self.storage = SimpleNamespace(db=None)

    def resolve_scope(self, value: str) -> str:
        return value

    def identity_from_event(self, event: Event) -> SimpleNamespace:
        del event
        return SimpleNamespace(global_user_id="qq:tester")


def request(text: str) -> AssistantTaskRequest:
    return AssistantTaskRequest(
        event=Event(),
        text=text,
        wake=SimpleNamespace(source="plana_name_mention"),
        decision=SimpleNamespace(
            intent="tool_execution_candidate",
            route="task_candidate",
        ),
        turn_context=SimpleNamespace(
            scope_id="aiocqhttp:GroupMessage:acceptance",
            actor_id="qq:tester",
        ),
    )


async def main() -> None:
    DOMAIN_PLUGINS.replace(
        (
            DomainPluginDescriptor(
                schema_version=1,
                domain_id="ncqq",
                owner="acceptance",
                profile="ncqq_plugin",
                tool_name="ncqq_manager",
                service_ref="ncqq.production",
                direct_dispatch=True,
            ),
        )
    )
    router = AssistantTaskRouter(Runtime())
    domain_request = request("plana帮我看看ncqq状态")
    domain_result = await router.handle(domain_request)
    assert not domain_result.handled
    assert domain_result.reason == "single_domain_plugin_tool"
    assert getattr(domain_request.event, "_plana_native_tool_profile") == "ncqq_plugin"

    codex_request = request("帮我深入分析201实例最近的错误日志并给出修复方案")
    codex_result = await router.handle(codex_request)
    assert codex_result.handled and codex_result.stop_event
    assert "Codex" in codex_result.reply
    state = router.sessions.session(
        "aiocqhttp:GroupMessage:acceptance",
        "qq:tester",
    )
    assert state.latest_remote_authorization_pending
    assert state.latest_expected_capability in {"codex.interactive", "codex.long_task"}
    assert not hasattr(router.runtime, "secretary_workflows")
    print("assistant_task_broker_check=ok")


if __name__ == "__main__":
    asyncio.run(main())
