from __future__ import annotations

from ..database.db_manager import Subscription
from .candidate_analysis import analyze_search_candidates
from .cards import (
    candidate_list_card,
    subscription_change_card,
    subscription_confirm_card,
)
from .entity_resolver import resolve_up_reference
from .formatting import format_candidates
from .models import WorkflowRequest
from .pending import store_pending_task
from .resolver_stats import record_resolver_event
from .results import WorkflowResult
from .runtime import event_origin
from .selection import choose_confident_candidate, score_candidate
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
        candidate, error = await _candidate_from_uid(plugin, target)
        if error:
            return WorkflowResult(error)
        return await build_confirm_task(
            plugin,
            event,
            _request_with_sub_type(request, sub_type),
            candidate,
        )

    keyword = first_text(payload, "keyword", "query", "name") or target
    if not keyword:
        return "请提供 UP 主 UID 或搜索关键词。"

    resolved = await resolve_up_reference(plugin, event, keyword)
    if resolved and resolved.source != "uid":
        return await build_confirm_task(plugin, event, request, resolved.as_candidate())

    candidates, error = await search_up_candidates(keyword)
    if error:
        record_resolver_event(plugin, "error", source="bili_search")
        return error
    if not candidates:
        return f"未找到关键词“{keyword}”对应的 UP 主。"
    record_resolver_event(plugin, "bili_search", source="bili_user_search")

    selection = None
    if _can_auto_select_candidates(plugin, request):
        selection = await analyze_search_candidates(
            plugin,
            event,
            keyword,
            candidates,
            sub_type=sub_type,
        )
        if selection is None:
            selection = choose_confident_candidate(
                keyword,
                candidates,
                threshold=float(getattr(plugin, "ai_auto_select_confidence", 0.88)),
            )
    if selection:
        return await build_confirm_task(plugin, event, request, selection.candidate)

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
        + "\n\n引用这条消息回复序号即视为确认，会直接写入订阅；回复“取消”则不改动。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            format_candidates(candidates, title=f"请选择要订阅的 UP（{keyword}）")
            + "\n\n引用这条消息回复序号即视为确认，会直接写入订阅。"
        ),
        task_id=task_id,
        cards=[candidate_list_card(
            candidates,
            f"请选择要订阅的 UP: {keyword}",
            "引用这条消息回复序号即视为确认，会直接写入订阅。",
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
    target = first_text(payload, "uid", "target", "mid", "query", "keyword", "name")
    sub_type = normalize_sub_type(first_text(payload, "sub_type", "type") or "dynamic")
    if not target:
        return WorkflowResult("删除订阅需要明确 UID，或使用已确认过的简称/当前订阅名称。")

    if is_uid(target):
        uid = target
        resolved_candidate = None
    else:
        resolved = await resolve_up_reference(plugin, event, target)
        if not resolved:
            return await _remove_with_subscription_candidates(
                plugin,
                event,
                request,
                target,
                sub_type,
            )
        uid = resolved.uid
        resolved_candidate = resolved.as_candidate()

    existing = _matching_subscriptions(plugin, event, uid, sub_type)
    if not existing:
        return WorkflowResult(f"未找到订阅：UID={uid}, type={sub_type}")

    candidate = resolved_candidate or await _candidate_from_existing(plugin, uid, existing)
    return await build_remove_confirm_task(
        plugin,
        event,
        _request_with_sub_type(request, sub_type),
        candidate,
    )


async def _remove_with_subscription_candidates(
    plugin,
    event,
    request: WorkflowRequest,
    target: str,
    sub_type: str,
) -> WorkflowResult:
    candidates = _subscription_candidate_dicts(plugin, event, target, sub_type)
    if not candidates:
        return WorkflowResult("删除订阅需要明确 UID，或使用已确认过的简称/当前订阅名称。")

    selection = await analyze_search_candidates(
        plugin,
        event,
        target,
        candidates,
        sub_type=sub_type,
        intent="remove_subscription",
    )
    if selection is None:
        selection = choose_confident_candidate(
            target,
            candidates,
            threshold=float(getattr(plugin, "ai_candidate_analysis_confidence", 0.86)),
        )
    if selection:
        selected_type = str(selection.candidate.get("sub_type") or sub_type)
        return await build_remove_confirm_task(
            plugin,
            event,
            _request_with_sub_type(request, selected_type),
            selection.candidate,
        )

    task_id = await store_pending_task(
        plugin,
        event,
        _request_with_sub_type(request, sub_type),
        kind="up_candidates",
        payload={
            "keyword": target,
            "candidates": candidates,
            "mode": "remove_subscription",
            "sub_type": sub_type,
        },
    )
    text = (
        format_candidates(candidates, title=f"请选择要删除的订阅（{target}）")
        + "\n\n请引用这条消息回复序号；选择后还需要确认删除。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            format_candidates(candidates, title=f"请选择要删除的订阅（{target}）")
            + "\n\n引用这条消息回复序号即可选择候选；选择后还需要确认删除。"
        ),
        task_id=task_id,
        cards=[candidate_list_card(
            candidates,
            f"请选择要删除的订阅: {target}",
            "引用这条消息回复序号即可选择候选；确认前不会删除订阅。",
        )],
    )


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
        "请引用这条消息回复“确认”写入订阅，或回复“取消”放弃。"
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


async def build_remove_confirm_task(
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
        kind="confirm_remove_subscription",
        payload={"candidate": candidate, "sub_type": sub_type},
    )
    text = (
        f"已定位待删除订阅：{candidate.get('username')} | UID={candidate.get('uid')} | type={sub_type}\n"
        "请引用这条消息回复“确认删除”移除订阅，或回复“取消”放弃。"
    )
    return WorkflowResult(
        text=text,
        display_text=(
            f"已定位待删除订阅：{candidate.get('username')} | UID={candidate.get('uid')} | type={sub_type}\n"
            "引用这条消息回复“确认删除”移除订阅，或回复“取消”放弃。"
        ),
        task_id=task_id,
        cards=[subscription_confirm_card(
            username=str(candidate.get("username") or ""),
            face=str(candidate.get("face") or ""),
            uid=str(candidate.get("uid") or ""),
            sub_type=sub_type,
            action="remove",
        )],
    )


async def remove_subscription_by_uid(plugin, event, uid: str, sub_type: str) -> WorkflowResult:
    if sub_type not in {"dynamic", "live", "both"}:
        return WorkflowResult("sub_type 仅支持 dynamic、live 或 both。")
    if sub_type == "both":
        results = [
            await _remove_one(plugin, event, uid, "dynamic"),
            await _remove_one(plugin, event, uid, "live"),
        ]
        cards = [card for result in results for card in result.cards]
        return WorkflowResult("\n".join(result.text for result in results), cards)
    return await _remove_one(plugin, event, uid, sub_type)


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


async def _candidate_from_uid(plugin, uid: str) -> tuple[dict, str]:
    user_info = await plugin.parser.get_user_info(uid)
    if not user_info:
        return {}, f"无法获取 UID={uid} 的用户信息。"
    return {
        "uid": str(uid),
        "username": user_info.get("username") or str(uid),
        "face": user_info.get("face") or "",
        "follower": None,
    }, ""


async def _candidate_from_existing(plugin, uid: str, existing: list[Subscription]) -> dict:
    first = existing[0]
    face = ""
    try:
        user_info = await plugin.parser.get_user_info(uid) or {}
        face = user_info.get("face") or ""
    except Exception:
        face = ""
    return {
        "uid": str(uid),
        "username": getattr(first, "username", "") or str(uid),
        "face": face,
        "follower": None,
    }


def _matching_subscriptions(
    plugin,
    event,
    uid: str,
    sub_type: str,
) -> list[Subscription]:
    wanted = {"dynamic", "live"} if sub_type == "both" else {sub_type}
    target_id = event_origin(event)
    return [
        sub
        for sub in plugin.db.get_subscriptions(target_id)
        if sub.uid == str(uid) and sub.sub_type in wanted
    ]


def _subscription_candidate_dicts(
    plugin,
    event,
    keyword: str,
    sub_type: str,
) -> list[dict]:
    wanted = {"dynamic", "live"} if sub_type == "both" else {sub_type}
    rows = [
        {
            "uid": sub.uid,
            "username": sub.username,
            "sub_type": sub.sub_type,
            "tags": sub.tags or [],
            "face": "",
            "follower": None,
        }
        for sub in plugin.db.get_subscriptions(event_origin(event))
        if sub.sub_type in wanted
    ]
    return sorted(
        rows,
        key=lambda item: score_candidate(keyword, item, 0),
        reverse=True,
    )


def _request_with_sub_type(request: WorkflowRequest, sub_type: str) -> WorkflowRequest:
    return WorkflowRequest(
        workflow=request.workflow,
        target=request.target,
        params={**request.params, "sub_type": sub_type},
        source=request.source,
    )


def _default_categories(sub_type: str) -> list[int]:
    return [1, 2, 3, 4, 5, 6] if sub_type == "dynamic" else [1, 2, 3]


def _can_auto_select_candidates(plugin, request: WorkflowRequest) -> bool:
    if not getattr(plugin, "enable_ai_auto_select_candidates", True):
        return False
    return request.source in {"tool", "natural", "command"}
