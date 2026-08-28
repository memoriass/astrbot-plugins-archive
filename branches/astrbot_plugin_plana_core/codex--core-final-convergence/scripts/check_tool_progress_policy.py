from __future__ import annotations

import asyncio
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
ASTRBOT_ROOT = ROOT.parent / "AstrBot"
if ASTRBOT_ROOT.is_dir():
    sys.path.insert(0, str(ASTRBOT_ROOT))

from astrbot_plugin_plana_core.plugin.plugin_events import PlanaPluginEventMixin
from astrbot_plugin_plana_core.dialogue.domain_contracts import (
    DOMAIN_PLUGINS,
    DomainPluginDescriptor,
)


class Plugin(PlanaPluginEventMixin):
    def __init__(self) -> None:
        self.config = {
            "assistant_task_progress_enabled": True,
            "assistant_tool_progress_threshold_seconds": 1,
        }
        self._tool_progress_tasks = {}
        self._terminating = False


class Event:
    unified_msg_origin = "scope:test"

    def __init__(self) -> None:
        self.sent = []

    async def send(self, chain) -> None:
        self.sent.append(chain)


class Tool:
    def __init__(self, name: str) -> None:
        self.name = name


async def main() -> None:
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
    plugin = Plugin()
    event = Event()
    first = Tool("search-one")
    second = Tool("search-two")
    await plugin._handle_using_llm_tool(event, first, {})
    await asyncio.sleep(1.1)
    await plugin._handle_llm_tool_respond(event, first, {}, {})
    await plugin._handle_using_llm_tool(event, second, {})
    await asyncio.sleep(1.1)
    await plugin._handle_llm_tool_respond(event, second, {}, {})
    assert len(event.sent) == 1, event.sent
    event._plana_native_tool_profile = "ncqq_plugin"
    event._plana_domain_tool_call_count = 1
    response = type(
        "Response",
        (),
        {
            "completion_text": "收到，执行删除。",
            "reasoning_content": "unsafe",
            "result_chain": object(),
        },
    )()
    assert plugin._suppress_domain_tool_narration(event, response)
    assert response.completion_text == ""
    assert response.reasoning_content == ""
    assert response.result_chain is None
    print("tool_progress_policy_check=ok")


if __name__ == "__main__":
    asyncio.run(main())
