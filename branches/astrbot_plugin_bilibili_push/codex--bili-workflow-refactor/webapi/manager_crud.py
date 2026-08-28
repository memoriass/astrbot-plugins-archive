from __future__ import annotations

from ..core.http import HttpClient
from ..database.db_manager import Subscription
from .manager_response import error, ok
from .manager_serializers import (
    bool_payload,
    fetch_user_info,
    parse_categories,
    parse_cookies,
    parse_tags,
    serialize_account,
    serialize_subscription,
)


class SubscriptionCrud:
    def __init__(self, plugin):
        self.plugin = plugin

    async def create(self, payload: dict) -> dict:
        try:
            sub = await subscription_from_payload(payload)
        except ValueError as exc:
            return error(str(exc))
        if not self.plugin.db.add_subscription(sub):
            return error("订阅已存在或写入失败。")
        return ok({"subscription": serialize_subscription(sub)})

    async def update(self, payload: dict) -> dict:
        original_uid = str(payload.get("original_uid") or payload.get("uid") or "").strip()
        original_sub_type = str(
            payload.get("original_sub_type") or payload.get("sub_type") or ""
        ).strip()
        original_target_id = str(
            payload.get("original_target_id") or payload.get("target_id") or ""
        ).strip()
        if (
            not original_uid
            or original_sub_type not in {"dynamic", "live"}
            or not original_target_id
        ):
            return error("original_uid、original_sub_type、original_target_id 参数不完整。")
        try:
            sub = await subscription_from_payload(payload)
        except ValueError as exc:
            return error(str(exc))

        updated = self.plugin.db.update_subscription(
            original_uid,
            original_sub_type,
            original_target_id,
            sub,
        )
        if not updated:
            return error("未找到匹配订阅，或新订阅键已存在。")
        return ok({"subscription": serialize_subscription(sub)})

    def delete(self, payload: dict) -> dict:
        uid, sub_type, target_id = subscription_key(payload)
        if not uid or sub_type not in {"dynamic", "live"} or not target_id:
            return error("uid、sub_type、target_id 参数不完整。")
        if not self.plugin.db.remove_subscription(uid, sub_type, target_id):
            return error("未找到匹配订阅。")
        return ok({"removed": True})

    def set_enabled(self, payload: dict) -> dict:
        uid, sub_type, target_id = subscription_key(payload)
        enabled = bool(payload.get("enabled"))
        if not uid or sub_type not in {"dynamic", "live"} or not target_id:
            return error("uid、sub_type、target_id 参数不完整。")
        updated = self.plugin.db.set_subscription_enabled(
            uid,
            sub_type,
            target_id,
            enabled,
        )
        if not updated:
            return error("未找到匹配订阅。")
        return ok({"updated": True, "enabled": enabled})


class AccountCrud:
    async def upsert(self, payload: dict) -> dict:
        cookies = parse_cookies(payload)
        uid = str(payload.get("uid") or (cookies or {}).get("DedeUserID") or "").strip()
        if not uid:
            return error("uid 参数不能为空；新增账号时也可从 Cookie 的 DedeUserID 推断。")

        existing = {
            str(acc.get("uid")): acc
            for acc in await HttpClient.get_accounts()
        }.get(uid)
        if existing is None and cookies is None:
            return error("新增账号必须提供 cookies。")

        user_info = await fetch_user_info(uid)
        name = str(payload.get("name") or user_info.get("username") or uid).strip()
        face = str(payload.get("face") or user_info.get("face") or "").strip()
        valid = bool_payload(payload.get("valid"), True)
        await HttpClient.upsert_account(uid, name, face, cookies, valid)
        return ok({"account": serialize_account(await account_by_uid(uid))})

    async def delete(self, payload: dict) -> dict:
        uid = str(payload.get("uid") or "").strip()
        if not uid:
            return error("uid 参数不能为空。")
        if not await HttpClient.remove_account(uid):
            return error("未找到匹配账号。")
        return ok({"removed": True})

    async def set_valid(self, payload: dict) -> dict:
        uid = str(payload.get("uid") or "").strip()
        if not uid:
            return error("uid 参数不能为空。")
        valid = bool_payload(payload.get("valid"), True)
        if not await HttpClient.set_account_valid(uid, valid):
            return error("未找到匹配账号。")
        return ok({"updated": True, "valid": valid})


async def subscription_from_payload(payload: dict) -> Subscription:
    uid = str(payload.get("uid") or "").strip()
    sub_type = str(payload.get("sub_type") or "").strip()
    target_id = str(payload.get("target_id") or "").strip()
    if not uid or sub_type not in {"dynamic", "live"} or not target_id:
        raise ValueError("uid、sub_type、target_id 参数不完整。")

    user_info = await fetch_user_info(uid)
    username = str(payload.get("username") or user_info.get("username") or uid).strip()
    return Subscription(
        uid=uid,
        username=username,
        sub_type=sub_type,
        target_id=target_id,
        categories=parse_categories(payload.get("categories"), sub_type),
        tags=parse_tags(payload.get("tags")),
        enabled=bool_payload(payload.get("enabled"), True),
    )


def subscription_key(payload: dict) -> tuple[str, str, str]:
    return (
        str(payload.get("uid") or "").strip(),
        str(payload.get("sub_type") or "").strip(),
        str(payload.get("target_id") or "").strip(),
    )


async def account_by_uid(uid: str) -> dict:
    for account in await HttpClient.get_accounts():
        if str(account.get("uid")) == str(uid):
            return account
    return {"uid": uid}
