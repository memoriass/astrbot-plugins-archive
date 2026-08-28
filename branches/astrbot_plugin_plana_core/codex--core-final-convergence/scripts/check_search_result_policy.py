from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
ASTRBOT_ROOT = ROOT.parent / "AstrBot"
if ASTRBOT_ROOT.is_dir():
    sys.path.insert(0, str(ASTRBOT_ROOT))

from astrbot_plugin_plana_core.dialogue.tool_policy import intent_chat_tool_names
from astrbot_plugin_plana_core.dialogue.observer import DialogueObserver
from astrbot_plugin_plana_core.plugin.build_info import CORE_BUILD_ID
from astrbot_plugin_plana_core.plugin import plugin_events
from astrbot_plugin_plana_core.plugin import plugin_web
from astrbot_plugin_plana_core.presentation.search_results import (
    finalize_search_response,
    normalize_search_result,
    recommendation_card_document,
    search_query_from_message,
)


def _payload(count: int = 3, *, mikan: bool = False) -> dict:
    rows = []
    for index in range(count):
        host = "mikanani.me" if mikan and index == 0 else f"source{index}.example"
        rows.append(
            {
                "title": f"Result {index + 1}",
                "url": f"https://{host}/item/{index + 1}",
                "snippet": f"Evidence {index + 1}",
            }
        )
    return {"ok": True, "results": rows}


class Plugin(plugin_events.PlanaPluginEventMixin):
    context = SimpleNamespace(get_all_stars=lambda: [])


class Event:
    def __init__(self, query: str, result: dict) -> None:
        self._query = query
        self._plana_search_result = result
        self._plana_turn_id = "turn-test"
        self.extras = {}
        self.sent = []
        self.stopped = False

    def get_message_str(self) -> str:
        return self._query

    def set_extra(self, key: str, value: object) -> None:
        self.extras[key] = value

    async def send(self, chain) -> None:
        self.sent.append(chain)

    def stop_event(self) -> None:
        self.stopped = True


async def _delivery_checks() -> None:
    async def fake_render(_document: dict) -> str:
        return str(ROOT / "logo.png")

    original = plugin_events.render_document_to_file
    original_tool_render = plugin_web.render_document_to_file
    plugin_events.render_document_to_file = fake_render
    plugin_web.render_document_to_file = fake_render
    try:
        success = normalize_search_result(
            "Mikan anime ranking",
            _payload(3),
            attempts=1,
            searched_at="2026-07-15T05:00:00+00:00",
        )
        response = SimpleNamespace(completion_text="1. Result 1\n2. Result 2\n3. Result 3", result_chain=None)
        await Plugin()._finalize_native_search_response(
            Event("recommend anime ranking", success),
            response,
        )
        assert response.result_chain is not None
        assert response.result_chain.get_plain_text()
        assert len(response.result_chain.chain) == 2, response.result_chain.chain

        failure = normalize_search_result(
            "Mikan anime ranking",
            {"ok": False, "error": "TimeoutError"},
            attempts=2,
        )
        response = SimpleNamespace(
            completion_text="No shell. I will use memory rankings.",
            result_chain=None,
        )
        await Plugin()._finalize_native_search_response(
            Event("recommend anime ranking", failure),
            response,
        )
        assert "history" not in response.completion_text.lower()
        assert "\u5386\u53f2\u8bb0\u5fc6" in response.completion_text
        assert response.result_chain.get_plain_text() == response.completion_text
        assert len(response.result_chain.chain) == 1

        writes = []
        memory_event = SimpleNamespace(_plana_skip_response_memory=True)
        memory_response = SimpleNamespace(completion_text="live result")
        runtime = SimpleNamespace(record_response=lambda *_args: writes.append("written"))
        await DialogueObserver().record_response(runtime, memory_event, memory_response, None)
        assert writes == []

        direct_event = Event("recommend anime ranking", success)
        await plugin_web.PlanaNativeSearchTool(None)._deliver_result(direct_event, success)
        assert direct_event.stopped is True
        assert direct_event._plana_search_direct_delivery is True
        assert len(direct_event.sent) == 1
        assert len(direct_event.sent[0].chain) == 2
    finally:
        plugin_events.render_document_to_file = original
        plugin_web.render_document_to_file = original_tool_render


def main() -> int:
    assert CORE_BUILD_ID and CORE_BUILD_ID == CORE_BUILD_ID.strip()
    assert plugin_web._retryable_search_failure({"ok": False, "error": "ConnectionTimeoutError"})
    assert plugin_web._retryable_search_failure({"ok": False, "error": "TimeoutException"})
    assert intent_chat_tool_names("\u5e2e\u6211\u641c\u4e00\u4e0b Mikan \u8fd9\u5b63\u5ea6\u756a\u5267\u9ad8\u5206\u63a8\u8350") == {
        "ani_rss"
    }
    routed_query = search_query_from_message(
        "Plana \u5e2e\u6211\u641c\u4e00\u4e0b 2026\u5e747\u6708 \u590f\u5b63\u756a\u5267\u9ad8\u5206\u63a8\u8350\uff0c\u7b80\u77ed\u7ed9\u524d\u4e09\u540d\uff0c\u53ea\u8bfb\uff0c\u4e0d\u8981\u4ea4\u7ed9\u5916\u90e8\u6267\u884c\u5668"
    )
    assert routed_query.startswith("2026\u5e747\u6708 \u590f\u5b63\u756a\u5267\u9ad8\u5206\u63a8\u8350")
    assert "\u5916\u90e8\u6267\u884c\u5668" not in routed_query
    search_event = Event(
        "\u5e2e\u6211\u641c\u4e00\u4e0b 2026\u5e747\u6708 \u590f\u5b63\u756a\u5267\u9ad8\u5206\u63a8\u8350",
        {},
    )
    assert Plugin()._prepare_native_turn(search_event) == "search"
    assert search_event.extras["enable_streaming"] is False
    assert search_event._plana_native_tool_profile == "search"
    chat_event = Event("\u968f\u4fbf\u804a\u804a", {})
    assert Plugin()._prepare_native_turn(chat_event) == ""
    assert "enable_streaming" not in chat_event.extras
    narration_event = Event("search anime", {})
    narration_event._plana_native_tool_profile = "search"
    narration = SimpleNamespace(
        completion_text="I will search now",
        reasoning_content="checking tools",
        result_chain=object(),
        tools_call_name=["web_search_searxng"],
    )
    assert Plugin()._suppress_search_tool_narration(narration_event, narration) is True
    assert narration.completion_text == ""
    assert narration.reasoning_content == ""
    assert narration.result_chain is None
    success = normalize_search_result(
        "Mikan anime ranking",
        _payload(3),
        attempts=1,
        searched_at="2026-07-15T05:00:00+00:00",
    )
    assert success["status"] == "succeeded"
    assert success["items"][0]["mikan_status"] == "unverified"
    text = finalize_search_response(
        "First line\nNo shell tool; use memory instead.\nFinal answer",
        success,
    )
    assert "shell" not in text.lower()
    assert "First line" not in text
    assert "\u8bc4\u5206\uff1a\u672a\u9a8c\u8bc1" in text
    assert "\u4e0d\u628a\u5b83\u4eec\u58f0\u79f0\u4e3a\u201c\u9ad8\u5206\u524d\u4e09\u540d\u201d" in text
    generic = normalize_search_result("OpenAI latest news", _payload(3), attempts=1)
    generic_text = finalize_search_response("ignored", generic)
    assert "\u8bc4\u5206\uff1a" not in generic_text
    assert "Mikan" not in generic_text
    assert "\u68c0\u7d22\u65f6\u95f4\uff1a" in generic_text
    assert recommendation_card_document("anime ranking recommendation", success) is not None
    assert recommendation_card_document("OpenAI latest news", success) is None
    short = normalize_search_result("x", _payload(2), attempts=1)
    assert recommendation_card_document("anime ranking recommendation", short) is None
    assert recommendation_card_document("show image card", short) is not None
    unavailable = normalize_search_result(
        "x", {"ok": False, "error": "TimeoutError"}, attempts=2
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["items"] == []
    assert "\u5386\u53f2\u8bb0\u5fc6" in finalize_search_response("cached answer", unavailable)
    asyncio.run(_delivery_checks())
    print("search_result_policy_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
