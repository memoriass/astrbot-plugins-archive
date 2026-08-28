from __future__ import annotations

import time

from .models import COMPILED_WORKFLOWS


def format_workflow_list() -> str:
    lines = ["可用 Bilibili workflow："]
    for spec in COMPILED_WORKFLOWS.values():
        if spec.user_visible:
            lines.append(f"- {spec.workflow}: {spec.title} - {spec.purpose}")
    return "\n".join(lines)


def format_candidates(candidates: list[dict], *, title: str = "搜索结果") -> str:
    if not candidates:
        return f"{title}: 无候选。"
    lines = [f"{title}: 找到 {len(candidates)} 个候选"]
    for index, item in enumerate(candidates, start=1):
        uname = item.get("username") or item.get("uname") or ""
        uid = item.get("uid") or item.get("mid") or ""
        follower = item.get("follower")
        suffix = f" | 粉丝 {follower}" if follower not in (None, "") else ""
        lines.append(f"{index}. {uname} | UID={uid}{suffix}")
    return "\n".join(lines)


def format_subscriptions(subs) -> str:
    if not subs:
        return "当前会话暂无订阅。"

    grouped: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for sub in subs:
        grouped.setdefault(sub.uid, set()).add(sub.sub_type)
        names[sub.uid] = sub.username

    lines = ["当前会话订阅列表："]
    for uid in sorted(grouped.keys()):
        sub_types = "/".join(sorted(grouped[uid]))
        lines.append(f"- {names.get(uid, uid)} | UID={uid} | type={sub_types}")
    return "\n".join(lines)


def format_accounts(accounts: list[dict], current_index: int) -> str:
    if not accounts:
        return "当前未登录任何 Bilibili 账号。"
    lines = ["Bilibili 账号池状态："]
    for index, account in enumerate(accounts):
        active = "当前" if index == current_index else "备用"
        valid = _account_status_text(account)
        status_code = account.get("status_code")
        status = f"{valid}, code={status_code}" if status_code and valid != "冷却中" else valid
        lines.append(
            f"- [{active}] {account.get('name') or '-'} | UID={account.get('uid') or '-'} | {status}"
        )
    return "\n".join(lines)


def _account_status_text(account: dict) -> str:
    if not account.get("valid", True):
        return "失效"
    if int(account.get("cooldown_until") or 0) > int(time.time()):
        return "冷却中"
    return "有效"
