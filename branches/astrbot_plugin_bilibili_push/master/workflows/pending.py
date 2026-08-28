from __future__ import annotations

import re
import secrets
import time

from .models import (
    CANCEL_REPLIES,
    CONFIRM_REPLIES,
    REMOVE_CONFIRM_REPLIES,
    WorkflowRequest,
)
from .markers import decode_task_marker
from .runtime import event_message_text, event_origin, event_text_bundle
from .utils import normalize_reply


TASK_PREFIX = "bili"


async def store_pending_task(
    plugin,
    event,
    request: WorkflowRequest,
    *,
    kind: str,
    payload: dict,
) -> str:
    task_id = f"{TASK_PREFIX}{secrets.token_hex(4)}"
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
        "created_at": time.time(),
        **payload,
    }
    await plugin.pending_store.create(task)
    return task_id


async def run_continue_pending(plugin, event, request: WorkflowRequest) -> object:
    task_ref = _task_ref_from_request_or_event(request, event)
    action = _action_from_request_or_text(request, event_message_text(event), task_ref)
    if not task_ref:
        task_ref, ambiguous = await _single_pending_task_ref(plugin, event, action)
        if ambiguous:
            return "当前有多个待处理事项，请引用对应消息回复。"
        if not task_ref:
            return "请引用待处理消息回复序号、确认或取消。"

    task_id, matches = await plugin.pending_store.resolve(
        task_ref,
        origin=event_origin(event),
    )
    if matches:
        return "匹配到多个待处理事项，请引用对应消息回复。"
    if not task_id:
        return "待处理事项不存在或已过期。"

    task = await plugin.pending_store.get(task_id)
    if not task:
        return "待处理事项不存在或已过期。"

    if task.get("kind") == "up_candidates":
        return await _continue_candidates(plugin, event, request, task_id, task, action)
    if task.get("kind") == "confirm_add_subscription":
        return await _continue_add_confirm(plugin, event, task_id, task, action)
    if task.get("kind") == "confirm_remove_subscription":
        return await _continue_remove_confirm(plugin, event, task_id, task, action)
    if task.get("kind") == "confirm_live_check_all":
        return await _continue_live_check_all(plugin, event, task_id, action)
    return f"未知任务类型：{task.get('kind')}"


async def _continue_candidates(
    plugin,
    event,
    request,
    task_id: str,
    task: dict,
    action: str,
) -> object:
    if normalize_reply(action) in CANCEL_REPLIES:
        await plugin.pending_store.delete(task_id)
        return "已取消待处理事项。"

    candidates = task.get("candidates") or []
    index = _choice_index(action, len(candidates))
    if index is None:
        return f"请引用这条消息回复 1-{len(candidates)} 的序号，或回复“取消”。"

    candidate = candidates[index]
    await plugin.pending_store.delete(task_id)
    if task.get("mode") == "remove_subscription":
        from .subscription import build_remove_confirm_task

        next_request = WorkflowRequest(
            workflow="remove_subscription",
            target=str(candidate.get("uid") or ""),
            params={"sub_type": candidate.get("sub_type") or task.get("sub_type") or "dynamic"},
            source=request.source,
        )
        return await build_remove_confirm_task(plugin, event, next_request, candidate)

    if task.get("mode") != "add_subscription":
        alias = str(task.get("keyword") or "").strip()
        if alias:
            from .entity_resolver import learn_up_alias

            learn_up_alias(plugin, event, alias, candidate, source="search_selection")
        return f"已选择：{candidate.get('username')} | UID={candidate.get('uid')}"

    from .subscription import build_confirm_task

    next_request = WorkflowRequest(
        workflow="add_subscription",
        target=str(candidate.get("uid") or ""),
        params={
            "sub_type": task.get("sub_type") or "dynamic",
            "alias": task.get("keyword") or "",
        },
        source=request.source,
    )
    if _can_direct_confirm_candidate(request):
        from .subscription import add_subscription_by_uid

        result = await add_subscription_by_uid(
            plugin,
            event,
            str(candidate.get("uid") or ""),
            str(task.get("sub_type") or "dynamic"),
        )
        alias = str(task.get("keyword") or "").strip()
        if alias:
            from .entity_resolver import learn_up_alias

            learn_up_alias(plugin, event, alias, candidate, source="search_selection")
        return result
    return await build_confirm_task(plugin, event, next_request, candidate)


async def _continue_add_confirm(
    plugin,
    event,
    task_id: str,
    task: dict,
    action: str,
) -> object:
    normalized = normalize_reply(action)
    if normalized in CANCEL_REPLIES:
        await plugin.pending_store.delete(task_id)
        return "已取消待处理事项。"
    if normalized not in CONFIRM_REPLIES:
        return "请引用这条消息回复“确认”或“取消”。"

    candidate = task.get("candidate") or {}
    uid = str(candidate.get("uid") or "")
    sub_type = str(task.get("sub_type") or "dynamic")
    await plugin.pending_store.delete(task_id)

    from .subscription import add_subscription_by_uid

    result = await add_subscription_by_uid(plugin, event, uid, sub_type)
    alias = _alias_from_confirm_task(task)
    if alias:
        from .entity_resolver import learn_up_alias

        learn_up_alias(plugin, event, alias, candidate)
    return result


async def _continue_remove_confirm(
    plugin,
    event,
    task_id: str,
    task: dict,
    action: str,
) -> object:
    normalized = normalize_reply(action)
    if normalized in CANCEL_REPLIES:
        await plugin.pending_store.delete(task_id)
        return "已取消待处理事项。"
    if normalized not in REMOVE_CONFIRM_REPLIES:
        return "请引用这条消息回复“确认删除”或“取消”。"

    candidate = task.get("candidate") or {}
    uid = str(candidate.get("uid") or "")
    sub_type = str(task.get("sub_type") or "dynamic")
    await plugin.pending_store.delete(task_id)

    from .subscription import remove_subscription_by_uid

    return await remove_subscription_by_uid(plugin, event, uid, sub_type)


async def _continue_live_check_all(plugin, event, task_id: str, action: str) -> object:
    normalized = normalize_reply(action)
    if normalized in CANCEL_REPLIES:
        await plugin.pending_store.delete(task_id)
        return "已取消全部群直播检查。"
    if normalized not in CONFIRM_REPLIES:
        return "请引用这条消息回复“确认”或“取消”。"
    await plugin.pending_store.delete(task_id)

    from .manage import execute_live_check_all

    return await execute_live_check_all(plugin, event)


def _alias_from_confirm_task(task: dict) -> str:
    request = task.get("request") or {}
    params = request.get("params") or {}
    for key in ("alias", "query", "keyword", "target", "name"):
        value = params.get(key) if key != "target" else request.get("target")
        if value and str(value).strip():
            return str(value).strip()
    return str(task.get("keyword") or "").strip()


def _can_direct_confirm_candidate(request: WorkflowRequest) -> bool:
    return request.source == "pending" and request.params.get("via_reply") is True


def extract_task_ref(text: str) -> str:
    match = re.search(
        r"(?<![0-9A-Za-z_\u4e00-\u9fff])bili([0-9a-fA-F]{3,8})(?![0-9A-Za-z_\u4e00-\u9fff])",
        str(text or ""),
    )
    return f"bili{match.group(1).lower()}" if match else ""


def task_ref_from_text(text: str) -> str:
    marker = decode_task_marker(text)
    if marker:
        return marker
    return extract_task_ref(text)


def task_ref_from_event(event) -> str:
    for text in event_text_bundle(event):
        task_ref = task_ref_from_text(text)
        if task_ref:
            return task_ref
    return ""


def _task_ref_from_request_or_event(request: WorkflowRequest, event) -> str:
    for key in ("task_id", "task", "id", "target"):
        value = request.params.get(key) if key != "target" else request.target
        extracted = task_ref_from_text(str(value or ""))
        if extracted:
            return extracted
    return task_ref_from_event(event)


def _action_from_request_or_text(request: WorkflowRequest, text: str, task_ref: str) -> str:
    for key in ("choice", "selection", "index", "action", "confirm"):
        value = request.params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raw_text = str(text or "").strip()
    if task_ref and task_ref in raw_text:
        return raw_text.replace(task_ref, "", 1).strip()
    target = str(request.target or "").strip()
    if target and not task_ref_from_text(target):
        return target
    return raw_text


async def _single_pending_task_ref(plugin, event, action: str) -> tuple[str, bool]:
    if not looks_like_pending_action(action):
        return "", False
    tasks = await plugin.pending_store.list_tasks()
    origin = event_origin(event)
    matches = [
        str(task.get("task_id") or "")
        for task in tasks
        if task.get("origin") == origin and str(task.get("task_id") or "")
    ]
    if len(matches) == 1:
        return matches[0], False
    return "", len(matches) > 1


def looks_like_pending_action(action: str) -> bool:
    normalized = normalize_reply(action)
    if normalized in CANCEL_REPLIES or normalized in CONFIRM_REPLIES:
        return True
    if normalized in REMOVE_CONFIRM_REPLIES:
        return True
    return bool(
        re.fullmatch(
            r"(?:选|选择|第)?\s*\d{1,2}\s*(?:个|项)?",
            str(action or "").strip(),
        )
    )


def looks_like_standalone_pending_action(action: str) -> bool:
    normalized = normalize_reply(action)
    if normalized in {"确认", "确认删除", "取消", "放弃", "cancel"}:
        return True
    return bool(
        re.fullmatch(
            r"(?:选|选择|第)?\s*\d{1,2}\s*(?:个|项)?",
            str(action or "").strip(),
        )
    )


def _choice_index(action: str, max_index: int) -> int | None:
    normalized = normalize_reply(action)
    if normalized in CANCEL_REPLIES:
        return None
    match = re.search(r"(?:选|选择|第)?\s*(\d{1,2})\s*(?:个|项)?", str(action or ""))
    if not match:
        return None
    value = int(match.group(1))
    if not 1 <= value <= max_index:
        return None
    return value - 1
