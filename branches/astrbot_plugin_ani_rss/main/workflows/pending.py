from __future__ import annotations

from contextlib import suppress
import re
from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..ui.rendering import cleanup_rendered_cards
from .models import WorkflowRequest
from .utils import _first_text, normalize_reply


def event_origin(event: AstrMessageEvent) -> str:
    return str(
        getattr(event, "unified_msg_origin", "")
        or getattr(event, "session_id", "")
        or "",
    )


def event_message_text(event: AstrMessageEvent) -> str:
    text_getter = getattr(event, "get_message_str", None)
    if callable(text_getter):
        return str(text_getter() or "")
    return str(getattr(event, "message_str", "") or "")


def extract_task_ref(text: str) -> str:
    raw = str(text or "")
    if re.search(r"\bani-[0-9a-fA-F]{3,8}\b", raw):
        return ""
    full = _extract_task_id(raw)
    if full:
        return full
    prefixed = re.search(
        r"(?<![0-9A-Za-z_\u4e00-\u9fff])ani([0-9a-fA-F]{3,8})(?![0-9A-Za-z_\u4e00-\u9fff])",
        raw,
    )
    if prefixed:
        return f"ani{prefixed.group(1).lower()}"
    return ""


def resolve_pending_task(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> tuple[str, dict[str, Any] | None, str]:
    task_ref = _resolve_task_ref(event, request)
    if not task_ref:
        example = command_example(plugin, event, "ani<任务ID前后几位> <序号|确认|取消>")
        return "", None, f"继续 ANI-RSS 挂起任务需要 task_id。请引用带任务ID的消息，或使用 `{example}`。"

    resolver = getattr(plugin, "resolve_pending_task_id", None)
    if callable(resolver):
        task_id, matches = resolver(task_ref, origin=event_origin(event))
        if matches:
            short = "、".join(matches[:5])
            suffix = " ..." if len(matches) > 5 else ""
            return "", None, f"任务ID片段 `{task_ref}` 匹配到多个挂起任务: {short}{suffix}。请多输入几位。"
        if not task_id:
            return "", None, f"ANI-RSS 挂起任务不存在或已过期: {task_ref}"
    else:
        task_id = task_ref

    task = plugin.get_pending_task(task_id)
    if not task:
        return "", None, f"ANI-RSS 挂起任务不存在或已过期: {task_ref}"
    if not _task_origin_matches(event, task):
        return "", None, f"ANI-RSS 挂起任务不属于当前会话: {task_id}"
    return task_id, task, ""


def resolve_pending_action(event: AstrMessageEvent, request: WorkflowRequest) -> str:
    action = _first_text(
        {"target": request.target, **request.params},
        "choice",
        "selection",
        "index",
        "action",
        "confirm",
    )
    if action and not _extract_task_id(action):
        return action
    text = event_message_text(event).strip()
    return text or action


def extract_choice_index(action: str, max_index: int) -> int | None:
    normalized = normalize_reply(action)
    if not normalized:
        return None
    try:
        value = int(normalized)
    except ValueError:
        match = re.search(r"(?:选|选择|第)?\s*(\d{1,2})\s*(?:个|项|部)?", action)
        if not match:
            return None
        value = int(match.group(1))
    if not 1 <= value <= max_index:
        return None
    return value - 1


def command_example(plugin: Any, event: AstrMessageEvent, command: str) -> str:
    command_example_func = getattr(plugin, "command_example", None)
    if callable(command_example_func):
        with suppress(Exception):
            return command_example_func(command, event)
    return f"/{command}"


def pending_footer(plugin: Any, event: AstrMessageEvent, task_id: str, action: str) -> str:
    short_id = task_id.removeprefix("ani")[-4:]
    example = command_example(plugin, event, f"ani{short_id} {action}")
    return f"\n\n继续：引用回复“{action}”或发送 `{example}`。任务ID: {task_id}"


def pending_tool_summary(plugin: Any, event: AstrMessageEvent, task_id: str, action: str) -> str:
    short_id = task_id.removeprefix("ani")[-4:]
    example = command_example(plugin, event, f"ani{short_id} {action}")
    return (
        f"\n\n后台已挂起 task_id={task_id}。"
        f"下一步需要用户选择/确认：{action}。"
        f"如用户直接回复，可用 workflow=continue_pending、task_id={task_id}、choice/action=用户回复继续；"
        f"显式命令示例：{example}。"
    )


def request_from_task(task: dict[str, Any], source: str) -> WorkflowRequest:
    request_data = task.get("request") if isinstance(task.get("request"), dict) else {}
    return WorkflowRequest(
        workflow=str(request_data.get("workflow") or task.get("workflow") or ""),
        target=str(request_data.get("target") or ""),
        params=dict(request_data.get("params") or {}),
        source=source,
    )


def store_pending_task(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    *,
    kind: str,
    payload: dict[str, Any],
    task_id: str = "",
) -> tuple[str, dict[str, Any]]:
    task = {
        "task_id": task_id,
        "kind": kind,
        "origin": event_origin(event),
        "workflow": request.workflow,
        "request": {
            "workflow": request.workflow,
            "target": request.target,
            "params": dict(request.params),
        },
        "rendered_cards": [],
        **payload,
    }
    task_id = plugin.create_pending_task(task)
    stored = plugin.get_pending_task(task_id) or task
    return task_id, stored


def store_pending_rendered_cards(
    plugin: Any,
    task_id: str,
    request: WorkflowRequest,
) -> None:
    paths = list(request.rendered_cards)
    updater = getattr(plugin, "update_pending_task", None)
    if callable(updater):
        updater(task_id, {"rendered_cards": paths})
        return

    task = plugin.get_pending_task(task_id)
    if task is not None:
        task["rendered_cards"] = paths


def cleanup_task_cards(task: dict[str, Any] | None) -> None:
    if task:
        cleanup_rendered_cards(task.get("rendered_cards") or [])


def _event_text_bundle(event: AstrMessageEvent) -> str:
    parts = [event_message_text(event)]
    message_obj = getattr(event, "message_obj", None)
    for comp in getattr(message_obj, "message", []) or []:
        message_str = getattr(comp, "message_str", "")
        if message_str:
            parts.append(str(message_str))
        for reply_comp in getattr(comp, "chain", []) or []:
            text = getattr(reply_comp, "text", "")
            if text:
                parts.append(str(text))
    return "\n".join(part for part in parts if part)


def _extract_task_id(text: str) -> str:
    match = re.search(
        r"(?<![0-9A-Za-z_\u4e00-\u9fff])ani([0-9a-fA-F]{8})(?![0-9A-Za-z_\u4e00-\u9fff])",
        str(text or ""),
    )
    return f"ani{match.group(1).lower()}" if match else ""


def _resolve_task_ref(event: AstrMessageEvent, request: WorkflowRequest) -> str:
    task_id = _first_text(
        {"target": request.target, **request.params},
        "task_id",
        "task",
        "pending_task_id",
        "id",
        "target",
    )
    if task_id:
        extracted = extract_task_ref(task_id)
        return extracted or task_id.strip()
    return extract_task_ref(_event_text_bundle(event))


def _task_origin_matches(event: AstrMessageEvent, task: dict[str, Any]) -> bool:
    origin = str(task.get("origin") or "")
    return not origin or origin == event_origin(event)
