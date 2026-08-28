from __future__ import annotations

import re
from typing import Any

from astrbot.api.event import AstrMessageEvent


def message_event_from_tool_arg(event: Any) -> AstrMessageEvent:
    context = getattr(event, "context", None)
    actual_event = getattr(context, "event", None)
    return actual_event or event


def apply_tool_prompt_flags(event: Any, request: Any) -> None:
    if request.source != "tool":
        return
    text_getter = getattr(event, "get_message_str", None)
    text = text_getter() if callable(text_getter) else getattr(event, "message_str", "")
    if not isinstance(text, str):
        text = str(text or "")
    no_add = re.search(r"(?:只展示|先只|先看看|先看|看看|不要|不用|先不|无需|别).{0,20}(?:添加|下载|订阅|追番|加入|候选)", text)
    if no_add and request.workflow == "recommend_mikan_subscription":
        request.params.setdefault("preview_only", True)
    if no_add and request.workflow == "add_mikan_subscription":
        request.workflow = "search_mikan"


def help_text(plugin: Any, event: AstrMessageEvent) -> str:
    def cmd(command: str) -> str:
        return plugin.command_example(command, event)

    return (
        "ANI-RSS 订阅助手：\n"
        f"{cmd('anirss add_subscription <rss_url>')}       - 确认后添加 RSS 订阅\n"
        f"{cmd('anirss add_mikan_subscription <番名>')}    - 搜索 Mikan，选择番剧/字幕组后添加\n"
        f"{cmd('anirss recommend_mikan_subscription [query|year season]')} - 推荐筛选后添加\n"
        f"{cmd('anirss search_mikan <番名或Mikan链接>')}   - 搜索 Mikan 或查看字幕组 RSS\n"
        f"{cmd('anirss list_subscriptions [limit]')}       - 查看已启用订阅\n"
        f"{cmd('anirss refresh_subscription <id>')}        - 刷新单个订阅\n"
        f"{cmd('anirss refresh_all')}                      - 刷新全部订阅\n"
        f"{cmd('ani<任务ID前后几位> <序号|确认|取消>')}        - 继续挂起的 ANI-RSS 任务\n"
        f"{cmd('anirss check_status')}                     - 检查 ANI-RSS 连接"
    )
