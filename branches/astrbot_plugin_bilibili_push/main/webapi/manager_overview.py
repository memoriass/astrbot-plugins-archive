from __future__ import annotations

import asyncio

from ..core.avatar_cache import fetch_avatar_map
from ..core.http import HttpClient
from .manager_serializers import (
    NO_FACE,
    serialize_account,
    serialize_pending_task,
    serialize_subscription,
    serialize_target,
)


class ManagerOverviewService:
    def __init__(self, plugin):
        self.plugin = plugin

    async def build(self) -> dict:
        subscriptions = await self._enrich_subscriptions([
            serialize_subscription(sub)
            for sub in self.plugin.db.get_subscriptions()
        ])
        accounts = [serialize_account(acc) for acc in await HttpClient.get_accounts()]
        targets = [serialize_target(target) for target in self.plugin.db.get_targets()]
        pending_tasks = [
            serialize_pending_task(task)
            for task in await self.plugin.pending_store.list_tasks()
        ]
        return {
            "diagnostics": self._diagnostics(
                subscriptions,
                accounts,
                pending_tasks,
                targets,
            ),
            "subscriptions": subscriptions,
            "accounts": accounts,
            "targets": targets,
            "pending_tasks": pending_tasks,
        }

    def _diagnostics(
        self,
        subscriptions: list[dict],
        accounts: list[dict],
        pending_tasks: list[dict],
        targets: list[dict],
    ) -> dict:
        dynamic_count = sum(1 for sub in subscriptions if sub["sub_type"] == "dynamic")
        live_count = sum(1 for sub in subscriptions if sub["sub_type"] == "live")
        target_enabled = {
            target["target_id"]: target.get("enabled", True)
            for target in targets
        }
        enabled_count = sum(
            1
            for sub in subscriptions
            if sub["enabled"] and target_enabled.get(sub["target_id"], True)
        )
        enabled_targets = sum(1 for target in targets if target.get("enabled", True))
        valid_accounts = sum(1 for acc in accounts if acc.get("available", True))
        return {
            "check_interval": self.plugin.check_interval,
            "dynamic_check_interval": self.plugin.dynamic_check_interval,
            "live_check_interval": self.plugin.live_check_interval,
            "risk_cooldown_sec": self.plugin.risk_cooldown_sec,
            "enable_link_parser": self.plugin.enable_link_parser,
            "enable_ai_tools": self.plugin.enable_ai_tools,
            "subscriptions": len(subscriptions),
            "enabled_subscriptions": enabled_count,
            "dynamic_subscriptions": dynamic_count,
            "live_subscriptions": live_count,
            "targets": len(targets),
            "enabled_targets": enabled_targets,
            "accounts": len(accounts),
            "valid_accounts": valid_accounts,
            "pending_tasks": len(pending_tasks),
        }

    async def _enrich_subscriptions(self, subscriptions: list[dict]) -> list[dict]:
        uids = sorted({sub["uid"] for sub in subscriptions if sub.get("uid")})
        face_map, live_status_map = await asyncio.gather(
            self._fetch_face_map(uids),
            self._fetch_live_status_map(subscriptions),
        )
        for sub in subscriptions:
            uid = sub.get("uid") or ""
            sub["face"] = face_map.get(uid, NO_FACE)
            sub["is_live"] = live_status_map.get(uid, False)
        return subscriptions

    async def _fetch_face_map(self, uids: list[str]) -> dict[str, str]:
        return await fetch_avatar_map(self.plugin, uids)

    async def _fetch_live_status_map(self, subscriptions: list[dict]) -> dict[str, bool]:
        live_uids = sorted({
            sub["uid"]
            for sub in subscriptions
            if sub.get("uid") and sub.get("sub_type") == "live"
        })
        if not live_uids:
            return {}
        try:
            live_infos = await self.plugin.scheduler.live_platform.batch_get_status(live_uids)
            return {str(info.uid): info.live_status == 1 for info in live_infos}
        except Exception:
            return {}
