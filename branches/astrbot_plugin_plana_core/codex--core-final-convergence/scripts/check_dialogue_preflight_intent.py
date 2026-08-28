from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.service import DialogueService


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


class FakeRuntime:
    def __init__(self) -> None:
        self.config = {
            "enable_dialogue_wake_state": True,
            "dialogue_wake_words": "plana",
            "dialogue_response_preflight_enabled": True,
            "dialogue_response_preflight_timeout_seconds": 0.2,
        }
        self.memory_plan_calls = 0
        self.concept_select_calls = 0

    def resolve_scope(self, _origin: str) -> str:
        return "scope"

    def status_text(self) -> str:
        return "status"

    def user_status_text(self) -> str:
        return "status"

    async def plan_memory_query(self, text: str, _provider):
        self.memory_plan_calls += 1
        return SimpleNamespace(should_retrieve=False, query=text)

    async def select_concept_nodes_for_prompt(self, _query: str, _provider) -> list[object]:
        self.concept_select_calls += 1
        return []

    def build_prompt_for_event(
        self,
        _event,
        _query: str,
        *,
        concept_nodes=None,
        **_kwargs,
    ) -> str:
        _ = concept_nodes
        return "prompt context"

class FakeEvent:
    is_at_or_wake_command = False
    call_llm = False

    def __init__(
        self,
        text: str,
        *,
        wake: bool = True,
        at: bool = False,
        call_llm: bool = False,
    ) -> None:
        self.text = text
        self.is_wake = wake
        self.is_at_or_wake_command = at
        self.call_llm = call_llm
        self.unified_msg_origin = "platform:GroupMessage:model"

    def get_message_str(self) -> str:
        return self.text

    def get_message_type(self) -> str:
        return "GroupMessage"

    def get_sender_id(self) -> str:
        return "tester"

    def get_sender_name(self) -> str:
        return "Tester"

    def is_private_chat(self) -> bool:
        return False


class FakePreflightProvider:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    async def text_chat(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(completion_text=self.payload)


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.active = True


class FakeToolSet:
    def __init__(self, names: list[str]) -> None:
        self.tools = [FakeTool(name) for name in names]

    def add_tool(self, tool: FakeTool) -> None:
        self.tools = [existing for existing in self.tools if existing.name != tool.name]
        self.tools.append(tool)

    def names(self) -> list[str]:
        return [tool.name for tool in self.tools]

    def openai_schema(self, *args, **kwargs) -> list[dict]:
        _ = args, kwargs
        return [{"name": tool.name} for tool in self.tools]

    def anthropic_schema(self) -> list[dict]:
        return [{"name": tool.name} for tool in self.tools]

    def google_schema(self) -> dict:
        return {"function_declarations": [{"name": tool.name} for tool in self.tools]}

    def get_light_tool_set(self):
        return FakeToolSet([tool.name for tool in self.tools if tool.active])

    def get_param_only_tool_set(self):
        return FakeToolSet([tool.name for tool in self.tools if tool.active])

    def __bool__(self) -> bool:
        return bool(self.tools)


class FakeToolManager:
    def __init__(self, names: list[str]) -> None:
        self.tools = {name: FakeTool(name) for name in names}

    def get_func(self, name: str):
        return self.tools.get(name)


class FakeAstrContext:
    def __init__(self, manager: FakeToolManager) -> None:
        self.manager = manager

    def get_llm_tool_manager(self):
        return self.manager


def fake_tool_prompt() -> str:
    return (
        "system\n"
        "## Skills\n\n"
        "You have specialized skills, stored in `SKILL.md` files.\n"
        "7. **Failure handling** — If a skill cannot be applied, state the "
        "issue clearly and continue with the best alternative.\n"
        "Current workspace you can use: `/tmp/work`\n"
        "Unless the user explicitly specifies a different directory, perform "
        "all file-related operations in this workspace.\n"
        "When using tools: never return an empty response; briefly explain the "
        "purpose before calling a tool; follow the tool schema exactly and do "
        "not invent parameters; after execution, briefly summarize the result "
        "for the user; keep the conversation style consistent.\n"
        "tail"
    )


def check_main_does_not_stop_without_reply() -> None:
    source = "\n".join(
        [
            (ROOT / "main.py").read_text(encoding="utf-8"),
            (ROOT / "plugin" / "plugin_events.py").read_text(encoding="utf-8"),
        ]
    )
    require(
        "if outcome.reply:" in source
        and "if outcome.render_document:" in source
        and "yield event.plain_result(outcome.reply)" in source
        and "if outcome.stop_event:\n                event.stop_event()" in source,
        "active_message_should_stop_only_after_non_empty_reply",
    )
    require(
        "Plana dialogue requested stop without reply" in source,
        "active_message_empty_stop_warning_missing",
    )


async def main() -> None:
    runtime = FakeRuntime()
    service = DialogueService(runtime)
    try:
        reply = await service.dispatch_message(
            FakeEvent("plana are you online"),
            provider={
                "preflight": FakePreflightProvider(
                    '{"respond": true, "action": "status_query", "reason": "online_status"}'
                )
            },
        )
        require(reply == "status", f"model_intent_reply={reply}")

        outcome = await service.dispatch_event(
            FakeEvent("plana is only mentioned as a name"),
            provider={
                "preflight": FakePreflightProvider(
                    '{"respond": false, "action": "ignore", "reason": "third_person"}'
                )
            },
        )
        require(outcome.reply == "", f"model_ignore_reply={outcome.reply}")
        require(not outcome.stop_event, "model_ignore_should_not_consume_passive_wake")

        call_llm_ignored = await service.dispatch_event(
            FakeEvent("plana测试模型连通性", wake=True, call_llm=True),
            provider={
                "preflight": FakePreflightProvider(
                    '{"respond": false, "action": "ignore", "reason": "ambiguous_test"}'
                )
            },
        )
        require(call_llm_ignored.reply == "", f"call_llm_ignore_reply={call_llm_ignored.reply}")
        require(
            not call_llm_ignored.stop_event,
            "call_llm_ignore_should_let_default_llm_continue",
        )

        default_provider = FakePreflightProvider(
            '{"respond": false, "action": "ignore", "reason": "should_not_run"}'
        )
        no_dedicated_preflight = await service.dispatch_event(
            FakeEvent("plana 你现在能正常聊天吗", wake=True, at=True),
            provider={"default": default_provider, "planner": default_provider},
        )
        require(
            default_provider.calls == 0,
            "preflight_must_not_fallback_to_default_or_planner_provider",
        )
        require(
            no_dedicated_preflight.reply == "",
            f"default_provider_preflight_reply={no_dedicated_preflight.reply}",
        )

        infix_mikan_event = FakeEvent(
            "那plana再调用一下mikan检索本季度高分番剧测试一下",
            wake=False,
            at=False,
        )
        infix_mikan_event.unified_msg_origin = "platform:GroupMessage:mikan-infix"
        outcome = await service.dispatch_event(infix_mikan_event, provider=None)
        behavior = getattr(infix_mikan_event, "_plana_behavior_decision", None)
        require(
            getattr(behavior, "capability", "") == "ani_plugin",
            f"infix_mikan_should_select_ani_plugin={behavior}",
        )
        require(outcome.reply == "", f"infix_mikan_should_defer_to_domain_plugin={outcome.reply}")
        require(not outcome.stop_event, "infix_mikan_service_layer_should_not_consume_domain_turn")
        require(
            infix_mikan_event.is_at_or_wake_command,
            "infix_mikan_domain_route_should_resume_llm_for_plugin_tool",
        )

        tool_request = SimpleNamespace(
            system_prompt="system",
            func_tool=FakeToolSet(
                ["plana_recall_memory", "astrbot_execute_shell", "run_browser_skill"]
            ),
        )
        await service.inject_prompt(FakeEvent("delete all memory"), tool_request, provider=None)
        require(
            tool_request.func_tool is not None,
            "chat_recall_tool_should_remain",
        )
        chat_tool_names = [
            str(getattr(item, "name", item)) for item in tool_request.func_tool.names()
        ]
        require(
            chat_tool_names == ["plana_recall_memory"],
            f"chat_tool_allowlist_mismatch={chat_tool_names}",
        )

        blocked_tool_request = SimpleNamespace(
            system_prompt=fake_tool_prompt(),
            func_tool=FakeToolSet(["astrbot_execute_shell", "run_browser_skill"]),
            contexts=[
                {
                    "role": "assistant",
                    "content": "trying shell",
                    "tool_calls": [
                        {"function": {"name": "astrbot_execute_shell"}},
                    ],
                },
                {"role": "tool", "name": "astrbot_execute_shell", "content": "denied"},
            ],
        )
        await service.inject_prompt(
            FakeEvent("delete all memory"),
            blocked_tool_request,
            provider=None,
        )
        require(
            blocked_tool_request.func_tool is not None,
            "blocked_chat_tools_should_keep_runner_safe_toolset",
        )
        require(
            blocked_tool_request.func_tool.names() == [],
            "blocked_chat_tools_should_hide_names",
        )
        require(
            blocked_tool_request.func_tool.openai_schema() == [],
            "blocked_chat_tools_should_expose_empty_schema",
        )
        require(
            blocked_tool_request.func_tool.get_light_tool_set().names() == [],
            "blocked_chat_tools_should_have_empty_light_schema",
        )
        require(blocked_tool_request.contexts == [], "blocked_tool_history_leaked")

        mikan_request = SimpleNamespace(
            system_prompt=fake_tool_prompt(),
            func_tool=FakeToolSet(
                ["plana_recall_memory", "ani_rss", "astrbot_execute_shell"]
            ),
            extra_user_content_parts=[],
            contexts=[
                {
                    "role": "assistant",
                    "content": "trying tools",
                    "tool_calls": [
                        {"function": {"name": "astrbot_execute_shell"}},
                        {"function": {"name": "ani_rss"}},
                    ],
                },
                {"role": "tool", "name": "astrbot_execute_shell", "content": "denied"},
            ],
        )
        before_memory_plan = runtime.memory_plan_calls
        before_concept_select = runtime.concept_select_calls
        await service.inject_prompt(
            FakeEvent("那plana再调用一下mikan检索本季度高分番剧测试一下"),
            mikan_request,
            provider=None,
        )
        require(
            mikan_request.func_tool.names() == ["ani_rss"],
            f"mikan_should_only_allow_ani_tool={mikan_request.func_tool.names()}",
        )
        require(
            "astrbot_execute_shell" not in str(mikan_request.contexts),
            "mikan_shell_history_leaked",
        )
        require(
            "[Plana controlled tool route]" in mikan_request.system_prompt
            and "Call only `ani_rss`" in mikan_request.system_prompt,
            "mikan_controlled_plugin_prompt_missing",
        )
        require(
            mikan_request.extra_user_content_parts == [],
            "mikan_prompt_should_not_use_user_parts_in_fake_event",
        )
        require(
            runtime.memory_plan_calls == before_memory_plan,
            "mikan_task_request_should_not_inject_dialogue_memory",
        )
        require(
            runtime.concept_select_calls == before_concept_select,
            "mikan_task_request_should_not_select_dialogue_concepts",
        )

        runtime.astr_context = FakeAstrContext(FakeToolManager(["ani_rss"]))
        recovered_mikan_request = SimpleNamespace(
            system_prompt=fake_tool_prompt(),
            func_tool=FakeToolSet(["plana_recall_memory", "astrbot_execute_shell"]),
            extra_user_content_parts=[],
            contexts=[],
        )
        await service.inject_prompt(
            FakeEvent("那plana再调用一下mikan检索本季度高分番剧测试一下"),
            recovered_mikan_request,
            provider=None,
        )
        require(
            recovered_mikan_request.func_tool.names() == ["ani_rss"],
            "mikan_tool_should_be_recovered_from_manager="
            f"{recovered_mikan_request.func_tool.names()}",
        )

        check_main_does_not_stop_without_reply()
    finally:
        await service.stop()
    print("dialogue_preflight_intent_check=ok")


if __name__ == "__main__":
    asyncio.run(main())
