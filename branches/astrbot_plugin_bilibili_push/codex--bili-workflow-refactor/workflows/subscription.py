from __future__ import annotations

from ..database.db_manager import Subscription
from .cards import (
    candidate_list_card,
    subscription_change_card,
    subscription_confirm_card,
)
from .formatting import format_candidates
from .models import WorkflowRequest
from .pending import store_pending_task
from .results import WorkflowResult
from .runtime import event_origin
from .selection import choose_confident_candidate
from .search import search_up_candidates
from .utils import first_text, is_uid, normalize_sub_type


async def run_add_subscription(
    plugin,
    event,
    request: WorkflowRequest,
) -> WorkflowResult | str:
    payload = {"target": request.target, **request.params}
    target = first_text(payload, "uid", "target", "mid")
    sub_type = normalize_sub_type(first_text(payload, "sub_type", "type") or "dynamic")
    if is_uid(target):
        return await add_subscription_by_uid(plugin, event, target, sub_type)

    keyword = first_text(payload, "keyword", "query", "name") or target
    if not keyword:
        return "请提供 UP 主 UID 或搜索关键词。"

    candidates, error = await search_up_candidates(keyword)
    if error:
        return error
    if not candidates:
        return f"未找到关键词“{keyword}”对应的 UP 主。"

    selection = choose_confident_candidate(
        keyword,
        candidates,
        threshold=float(getattr(plugin, "ai_auto_select_confidence", 0.88)),
    ) if _can_auto_select_candidates(plugin, request) else None
    if selection:
        result = await build_confirm_task(plugin, event, request, selection.candidate)
        base_display = result.display_text or result.text
        prefix = (
            "已根据候选匹配度自动选择："
            f"{selection.candidate.get('username')} | UID={selection.candidate.get('uid')} "
            f"| 置信度 {selection.confidence:.0%}\n"
            f"依据：{selection.reason}。\n"
            "仍需你确认后才会写入订阅。\n\n"
        )
        result.text = prefix + result.text
        result.display_text = prefix + base_display
        return result

    task_id = await store_pending_task(
        plugin,
        event,
        request,
        kind="up_candidates",
        payload={
            "keyword": keyword,
            "candidates": candidates,
            "mode": "add_subscription",
            "sub_type": sub_type,
        },
    )
    text = (
        format_candidates(candidates, title=f"请选择要订阅的 UP（{keyword}）")
        + f"\n\n任务ID: {task_id}\n"
        + f"发送 `bili{task_id[-4:]} <序号>` 选择候选；选择后还需要确认才会写入订阅。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            format_candidates(candidates, title=f"请选择要订阅的 UP（{keyword}）")
            + "\n\n引用这条消息回复序号即可选择候选；选择后还需要确认才会写入订阅。"
        ),
        task_id=task_id,
        cards=[candidate_list_card(
            candidates,
            f"请选择要订阅的 UP: {keyword}",
            "引用这条消息回复序号即可选择候选；确认前不会写入订阅。",
        )],
    )


async def add_subscription_by_uid(plugin, event, uid: str, sub_type: str) -> WorkflowResult:
    if sub_type not in {"dynamic", "live", "both"}:
        return WorkflowResult("sub_type 仅支持 dynamic、live 或 both。")

    user_info = await plugin.parser.get_user_info(uid)
    if not user_info:
        return WorkflowResult(f"无法获取 UID={uid} 的用户信息。")

    types = ["dynamic", "live"] if sub_type == "both" else [sub_type]
    target_id = event_origin(event)
    existing = plugin.db.get_subscriptions(target_id)
    messages = []
    cards = []
    for one_type in types:
        if any(sub.uid == str(uid) and sub.sub_type == one_type for sub in existing):
            messages.append(f"订阅已存在：{user_info['username']} ({uid}) [{one_type}]")
            continue
        sub = Subscription(
            uid=uid,
            username=user_info["username"],
            sub_type=one_type,
            target_id=target_id,
            categories=_default_categories(one_type),
            tags=[],
            enabled=True,
        )
        if plugin.db.add_subscription(sub):
            messages.append(f"已添加订阅：{user_info['username']} ({uid}) [{one_type}]")
            cards.append(subscription_change_card(
                username=user_info["username"],
                face=user_info.get("face") or "",
                uid=uid,
                sub_type=one_type,
                action="ADDED",
            ))
        else:
            messages.append(f"写入订阅失败或已存在：{user_info['username']} ({uid}) [{one_type}]")
    return WorkflowResult("\n".join(messages), cards=cards)


async def run_remove_subscription(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    payload = {"target": request.target, **request.params}
    uid = first_text(payload, "uid", "target", "mid")
    sub_type = normalize_sub_type(first_text(payload, "sub_type", "type") or "dynamic")
    if not is_uid(uid):
        return WorkflowResult("删除订阅需要明确 UID。")
    if sub_type == "both":
        results = [
            await _remove_one(plugin, event, uid, "dynamic"),
            await _remove_one(plugin, event, uid, "live"),
        ]
        cards = [card for result in results for card in result.cards]
        return WorkflowResult("\n".join(result.text for result in results), cards)
    return await _remove_one(plugin, event, uid, sub_type)


async def build_confirm_task(
    plugin,
    event,
    request: WorkflowRequest,
    candidate: dict,
) -> WorkflowResult:
    sub_type = normalize_sub_type(str(request.params.get("sub_type") or "dynamic"))
    task_id = await store_pending_task(
        plugin,
        event,
        request,
        kind="confirm_add_subscription",
        payload={"candidate": candidate, "sub_type": sub_type},
    )
    text = (
        f"已选择：{candidate.get('username')} | UID={candidate.get('uid')} | type={sub_type}\n"
        f"任务ID: {task_id}\n"
        f"发送 `bili{task_id[-4:]} 确认` 写入订阅，或发送 `bili{task_id[-4:]} 取消` 放弃。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            f"已选择：{candidate.get('username')} | UID={candidate.get('uid')} | type={sub_type}\n"
            "引用这条消息回复“确认”写入订阅，或回复“取消”放弃。"
        ),
        task_id=task_id,
        cards=[subscription_confirm_card(
            username=str(candidate.get("username") or ""),
            face=str(candidate.get("face") or ""),
            uid=str(candidate.get("uid") or ""),
            sub_type=sub_type,
        )],
    )


async def _remove_one(plugin, event, uid: str, sub_type: str) -> WorkflowResult:
    target_id = event_origin(event)
    existing = plugin.db.get_subscriptions(target_id)
    current = next(
        (sub for sub in existing if sub.uid == str(uid) and sub.sub_type == sub_type),
        None,
    )
    ok = plugin.db.remove_subscription(uid, sub_type, target_id)
    if not ok:
        return WorkflowResult(f"未找到订阅：UID={uid}, type={sub_type}")

    user_info = await plugin.parser.get_user_info(uid) or {}
    username = (
        getattr(current, "username", "")
        or user_info.get("username")
        or uid
    )
    card = subscription_change_card(
        username=username,
        face=user_info.get("face") or "",
        uid=uid,
        sub_type=sub_type,
        action="REMOVED",
    )
    return WorkflowResult(f"已删除订阅：{username} ({uid}) [{sub_type}]", [card])


def _default_categories(sub_type: str) -> list[int]:
    return [1, 2, 3, 4, 5, 6] if sub_type == "dynamic" else [1, 2, 3]


def _can_auto_select_candidates(plugin, request: WorkflowRequest) -> bool:
    if not getattr(plugin, "enable_ai_auto_select_candidates", True):
        return False
    return request.source in {"tool", "natural"}
