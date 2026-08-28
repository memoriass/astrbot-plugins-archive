from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable

from ..core.http import HttpClient
from .results import WorkflowCard


NO_FACE = "http://i0.hdslb.com/bfs/face/member/noface.jpg"


def candidate_list_card(
    candidates: list[dict],
    title: str,
    note: str,
) -> WorkflowCard:
    return WorkflowCard(
        template_name="workflow_candidates.html.jinja",
        templates={
            "page_title": title,
            "note": note,
            "candidates": [
                {
                    "uid": item.get("uid") or item.get("mid") or "",
                    "username": item.get("username") or item.get("uname") or "",
                    "face": item.get("face") or NO_FACE,
                    "has_dynamic": True,
                    "has_live": True,
                    "is_live": False,
                    "status_label": f"候选 {index}",
                    "status_class": "badge-warn",
                }
                for index, item in enumerate(candidates, start=1)
            ],
        },
        selector=".workflow-board",
    )


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
        _fetch_face_map(subs_map.keys()),
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
) -> WorkflowCard:
    label = "直播" if sub_type == "live" else "动态"
    return WorkflowCard(
        template_name="workflow_confirm.html.jinja",
        templates={
            "username": username,
            "face": face or NO_FACE,
            "uid": uid,
            "sub_type": sub_type,
            "action_label": "待确认",
            "title": f"确认订阅{label}吗？",
            "summary": "确认后会写入当前会话；取消则不会改动订阅。",
            "confirm_text": "引用回复 确认",
            "cancel_text": "引用回复 取消",
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


async def _fetch_face_map(uids) -> dict[str, str]:
    uids = [str(uid) for uid in uids if uid]
    if not uids:
        return {}
    client = await HttpClient.get_client()

    async def fetch(uid: str) -> tuple[str, str]:
        face = NO_FACE
        try:
            response = await client.get(
                "https://api.bilibili.com/x/web-interface/card",
                params={"mid": uid},
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    face = data.get("data", {}).get("card", {}).get("face") or face
        except Exception:
            pass
        return uid, face

    return dict(await asyncio.gather(*[fetch(uid) for uid in uids]))


async def _fetch_live_status_map(plugin, rows: Iterable[dict]) -> dict[str, bool]:
    live_uids = [str(row["uid"]) for row in rows if row.get("has_live")]
    if not live_uids:
        return {}
    try:
        live_infos = await plugin.scheduler.live_platform.batch_get_status(live_uids)
        return {str(info.uid): info.live_status == 1 for info in live_infos}
    except Exception:
        return {}
