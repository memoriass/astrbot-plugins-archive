from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain

from ..workflows import render_workflow_result, run_bili_workflow, workflow_from_tool
from ..workflows.runtime import message_event_from_tool_arg


class AiToolHandler:
    def __init__(self, star):
        self.star = star

    async def run_workflow(
        self,
        event,
        workflow: str,
        target: str = "",
        params: object = "",
    ) -> str:
        if not self.star.enable_ai_tools:
            return "AI 工具已关闭。"
        actual_event = message_event_from_tool_arg(event)
        request = workflow_from_tool(workflow, target, params)
        result = await run_bili_workflow(self.star, actual_event, request)
        await self._send_cards(actual_event, request, result)
        return result.text

    async def search_up(self, event, keyword: str) -> str:
        return await self.run_workflow(event, "search_up", keyword, {"keyword": keyword})

    async def add_subscription(
        self,
        event: AstrMessageEvent,
        target: str,
        sub_type: str,
    ) -> str:
        return await self.run_workflow(
            event,
            "add_subscription",
            target,
            {"query": target, "sub_type": sub_type},
        )

    async def remove_subscription(
        self,
        event: AstrMessageEvent,
        uid: str,
        sub_type: str,
    ) -> str:
        return await self.run_workflow(
            event,
            "remove_subscription",
            uid,
            {"uid": uid, "sub_type": sub_type},
        )

    async def list_subscriptions(self, event: AstrMessageEvent) -> str:
        return await self.run_workflow(event, "list_subscriptions")

    async def _send_cards(self, event: AstrMessageEvent, request, result) -> None:
        if not _should_present_tool_result(request):
            return
        if getattr(result, "card_intent", "") == "model_context":
            return
        if not getattr(result, "cards", None):
            return
        rendered = await render_workflow_result(event, self.star.renderer, result)
        if not getattr(rendered, "chain", None):
            return
        await event.send(MessageChain(chain=rendered.chain))


def _should_present_tool_result(request) -> bool:
    params = getattr(request, "params", {}) or {}
    return any(
        params.get(key) is True
        for key in ("present", "foreground", "show_card", "show_cards")
    )
