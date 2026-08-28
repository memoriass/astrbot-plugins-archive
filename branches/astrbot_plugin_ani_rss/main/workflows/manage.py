from __future__ import annotations

from collections.abc import AsyncIterator
import importlib.util
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .formatting import format_list
from .models import WorkflowRequest
from .runtime import interactive_reply, reply
from .utils import _first_text, _get_int


async def run_list_subscriptions(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        limit = _get_int(request.params, "limit", default=20)
        cached_list = getattr(plugin, "cached_list_ani", None)
        if callable(cached_list):
            anis = await cached_list()
        else:
            anis = await plugin.client(require_api_key=True).list_ani()
        anis = [ani for ani in anis if bool(ani.get("enable"))]
        text = format_list(anis, max(limit, 1))
        if request.source == "tool":
            yield reply(event, request, text)
            return
        yield await interactive_reply(plugin, event, request, text)
    except Exception as exc:
        yield reply(event, request, f"List subscriptions failed: {exc}")


async def run_refresh_subscription(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    subscription_id = _first_text(
        {"target": request.target, **request.params},
        "subscription_id",
        "id",
        "target",
    )
    if not subscription_id:
        yield reply(event, request, "refresh_subscription 需要 subscription_id。")
        return

    try:
        message = await plugin.client(require_api_key=True).refresh_ani(subscription_id)
        yield reply(event, request, message)
    except Exception as exc:
        yield reply(event, request, f"Refresh failed: {exc}")


async def run_refresh_all(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        message = await plugin.client(require_api_key=True).refresh_all()
        yield reply(event, request, message)
    except Exception as exc:
        yield reply(event, request, f"Refresh failed: {exc}")


async def run_check_status(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    try:
        await plugin.client().ping()
        about = await plugin.client().about()
        version = ""
        if isinstance(about.get("data"), dict):
            version = str(about["data"].get("version") or "")
        lines = ["ANI-RSS 连接正常"]
        if version:
            lines.append(f"服务版本: {version}")
        lines.extend(_runtime_status_lines(plugin))
        yield reply(event, request, "\n".join(lines))
    except Exception as exc:
        lines = [f"ANI-RSS 连接失败: {exc}"]
        lines.extend(_runtime_status_lines(plugin))
        yield reply(event, request, "\n".join(lines))


def _runtime_status_lines(plugin: Any) -> list[str]:
    lines: list[str] = []
    stats_func = getattr(plugin, "runtime_stats", None)
    if callable(stats_func):
        try:
            stats = stats_func()
            lines.append(f"SQLite: {stats.get('db_path') or '(unknown)'}")
            lines.append(f"挂起任务: {stats.get('pending_count', 0)}")
            lines.append(f"缓存条目: {stats.get('cache_count', 0)}")
            lines.append(f"偏好条目: {stats.get('preference_count', 0)}")
            lines.append(f"工具结果: {stats.get('tool_result_count', 0)}")
            cache_keys = stats.get("cache_keys")
            if isinstance(cache_keys, list) and cache_keys:
                names = [
                    f"{_short_cache_key(item.get('key'))}({item.get('ttl_seconds', 0)}s)"
                    for item in cache_keys[:5]
                    if isinstance(item, dict)
                ]
                if names:
                    lines.append("缓存预览: " + "、".join(names))
        except Exception as exc:
            lines.append(f"本地存储状态读取失败: {exc}")

    render_mode = getattr(plugin, "render_mode", lambda: "image")()
    renderer = "可用" if importlib.util.find_spec("pylitehtml") else "不可用，自动回退文本"
    lines.append(f"卡片发送模式: {render_mode}")
    lines.append(f"pylitehtml: {renderer}")
    return lines


def _short_cache_key(value: Any) -> str:
    text = str(value or "")
    if text.startswith("ani_rss:"):
        text = text.removeprefix("ani_rss:")
    if len(text) <= 32:
        return text
    return text[:29] + "..."
