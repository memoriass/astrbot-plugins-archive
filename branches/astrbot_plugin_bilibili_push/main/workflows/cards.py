from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable

from ..core.avatar_cache import NO_FACE, fetch_avatar_map
from .results import WorkflowCard


def candidate_list_card(
    candidates: list[dict],
    title: str,
    note: str,
    *,
    recommended_uid: str = "",
) -> WorkflowCard:
    return WorkflowCard(
        template_name="workflow_candidates.html.jinja",
        templates={
            "page_title": title,
            "note": note,
            "candidates": [
                _candidate_card_row(item, index, recommended_uid)
                for index, item in enumerate(candidates, start=1)
            ],
        },
        selector=".workflow-board",
    )


def _candidate_card_row(item: dict, index: int, recommended_uid: str) -> dict:
    uid = str(item.get("uid") or item.get("mid") or "")
    is_recommended = bool(recommended_uid) and uid == str(recommended_uid)
    sub_type = str(item.get("sub_type") or "")
    status_label = "AI 推荐" if is_recommended else f"候选 {index}"
    return {
        "uid": item.get("uid") or item.get("mid") or "",
        "username": item.get("username") or item.get("uname") or "",
        "face": item.get("face") or NO_FACE,
        "has_dynamic": sub_type in {"", "dynamic", "both"} or bool(item.get("has_dynamic")),
        "has_live": sub_type in {"", "live", "both"} or bool(item.get("has_live")),
        "is_live": False,
        "status_label": status_label,
        "status_class": "badge-live-on" if is_recommended else "badge-warn",
    }


async def subscription_list_card(plugin, subscriptions: Iterable) -> WorkflowCard:
    subs_map = {}
    for sub in subscriptions:
        subs_map.setdefault(
            sub.uid,
            {
                "uid": sub.uid,
                "username": sub.username,
                "has_dynamic": False,
                "has_live": False,
            },
        )
        if sub.sub_type == "dynamic":
            subs_map[sub.uid]["has_dynamic"] = True
        elif sub.sub_type == "live":
            subs_map[sub.uid]["has_live"] = True

    face_map, live_map = await asyncio.gather(
        _fetch_face_map(plugin, subs_map.keys()),
        _fetch_live_status_map(plugin, subs_map.values()),
    )
    rows = []
    for uid, item in subs_map.items():
        rows.append({
            **item,
            "face": face_map.get(str(uid), NO_FACE),
            "is_live": live_map.get(str(uid), False),
        })
    return WorkflowCard(
        template_name="sub_list.html.jinja",
        templates={"page_title": "当前会话订阅", "subs": rows},
    )


def account_status_card(accounts: list[dict], current_index: int) -> WorkflowCard:
    rows = []
    for index, account in enumerate(accounts):
        active = index == current_index
        valid = _account_available(account)
        rows.append({
            "uid": str(account.get("uid") or ""),
            "username": str(account.get("name") or "Bilibili 账号"),
            "face": str(account.get("face") or NO_FACE),
            "has_dynamic": False,
            "has_live": False,
            "is_live": False,
            "is_active_account": active,
            "status_label": _account_status_label(active, valid, account),
            "status_class": "badge-live-on" if valid else "badge-risk",
        })
    return WorkflowCard(
        template_name="sub_list.html.jinja",
        templates={"page_title": "Bilibili 账号池", "subs": rows},
    )


def subscription_change_card(
    *,
    username: str,
    face: str,
    uid: str,
    sub_type: str,
    action: str,
) -> WorkflowCard:
    return WorkflowCard(
        template_name="sub_add.html.jinja",
        templates={
            "username": username,
            "face": face or NO_FACE,
            "uid": uid,
            "sub_type": sub_type,
            "action": action,
        },
        viewport={"width": 400, "height": 400},
        selector=".card",
    )


def subscription_confirm_card(
    *,
    username: str,
    face: str,
    uid: str,
    sub_type: str,
    action: str = "add",
) -> WorkflowCard:
    label = {
        "live": "直播",
        "both": "动态和直播",
        "dynamic": "动态",
    }.get(sub_type, "动态")
    is_remove = action == "remove"
    action_label = {
        "add": "待确认",
        "remove": "待删除",
    }.get(action, "待确认")
    title = {
        "add": f"确认订阅{label}吗？",
        "remove": f"确认删除{label}订阅吗？",
    }.get(action, f"确认订阅{label}吗？")
    summary = {
        "add": "确认后会写入当前会话；取消则不会改动订阅。",
        "remove": "确认后会从当前会话移除；取消则不会改动订阅。",
    }.get(action, "确认后会写入当前会话；取消则不会改动订阅。")
    confirm_text = "引用回复 确认删除" if is_remove else "引用回复 确认"
    return WorkflowCard(
        template_name="workflow_confirm.html.jinja",
        templates={
            "username": username,
            "face": face or NO_FACE,
            "uid": uid,
            "sub_type": sub_type,
            "action_label": action_label,
            "title": title,
            "summary": summary,
            "confirm_text": confirm_text,
            "cancel_text": "引用回复 取消",
        },
        viewport={"width": 560, "height": 620},
        selector=".workflow-confirm",
    )


def operation_confirm_card(
    *,
    title: str,
    summary: str,
    username: str,
    uid: str = "-",
    action_label: str = "需要确认",
    confirm_text: str = "引用回复 确认",
    cancel_text: str = "引用回复 取消",
) -> WorkflowCard:
    return WorkflowCard(
        template_name="workflow_confirm.html.jinja",
        templates={
            "username": username,
            "face": NO_FACE,
            "uid": uid,
            "sub_type": "both",
            "action_label": action_label,
            "title": title,
            "summary": summary,
            "confirm_text": confirm_text,
            "cancel_text": cancel_text,
        },
        viewport={"width": 560, "height": 620},
        selector=".workflow-confirm",
    )


def _account_status_label(active: bool, valid: bool, account: dict) -> str:
    if _account_cooling(account):
        return "当前冷却" if active else "备用冷却"
    if active:
        return "当前有效" if valid else "当前失效"
    return "备用有效" if valid else "备用失效"


def _account_available(account: dict) -> bool:
    return bool(account.get("valid", True)) and not _account_cooling(account)


def _account_cooling(account: dict) -> bool:
    return int(account.get("cooldown_until") or 0) > int(time.time())


async def _fetch_face_map(plugin, uids) -> dict[str, str]:
    return await fetch_avatar_map(plugin, uids)


async def _fetch_live_status_map(plugin, rows: Iterable[dict]) -> dict[str, bool]:
    live_uids = [str(row["uid"]) for row in rows if row.get("has_live")]
    if not live_uids:
        return {}
    try:
        live_infos = await plugin.scheduler.live_platform.batch_get_status(live_uids)
        return {str(info.uid): info.live_status == 1 for info in live_infos}
    except Exception:
        return {}
