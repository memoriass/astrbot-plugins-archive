from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


def message_event_from_tool_arg(event: Any) -> Any:
    context = getattr(event, "context", None)
    return getattr(context, "event", None) or event


async def iter_tool_outputs(event: Any, outputs: AsyncIterator[Any]) -> AsyncIterator[Any]:
    direct_dispatch = bool(getattr(event, "_plana_domain_handler_executed", False))
    async for item in outputs:
        if direct_dispatch and isinstance(item, str):
            text = item.strip()
            if text:
                yield event.plain_result(text)
            continue
        if item is not None:
            yield item


def help_text() -> str:
    return (
        "Komga workflows:\n"
        "list_libraries | list_recent [limit=N] | search_series <query>\n"
        "series_detail <series_id> | list_books <series_id> [limit=N]\n"
        "on_deck [limit=N] | collections [limit=N] | readlists [limit=N]\n"
        "scan_library | analyze_library | refresh_library_metadata | "
        "refresh_series_metadata 仅生成待确认提案。"
    )

