from __future__ import annotations

import asyncio
import time
from typing import Any

from astrbot.api import logger
from quart import g, jsonify, request

from ..core.approval import claim_approval, list_approvals
from ..workflows.common import _container_name, _is_running, _list_containers, _manager_get

PLUGIN_ROUTE_PREFIXES = ("/ncqq_manager", "/astrbot_plugin_ncqq_manager")


class PageApiMixin:
    def register_page_apis(self) -> None:
        for prefix in PLUGIN_ROUTE_PREFIXES:
            self.context.register_web_api(
                f"{prefix}/dashboard/summary",
                self.page_dashboard_summary,
                ["GET"],
                "ncqq dashboard summary",
            )
            self.context.register_web_api(
                f"{prefix}/approvals/<approval_id>/approve",
                self.page_approval_approve,
                ["POST"],
                "approve ncqq pending approval",
            )
            self.context.register_web_api(
                f"{prefix}/approvals/<approval_id>/reject",
                self.page_approval_reject,
                ["POST"],
                "reject ncqq pending approval",
            )

    async def page_dashboard_summary(self):
        managers = await asyncio.gather(
            *(self._page_manager_summary(manager_id) for manager_id in self.manager_ids())
        )
        data = {
            "generated_at": time.time(),
            "default_manager": self.default_manager_id(),
            "dashboard": {
                "stream_threshold": _page_int_config(
                    self.config.get("dashboard_stream_threshold"), 10, 4, 30
                )
            },
            "managers": list(managers),
            "approvals": await self._page_approvals(),
            "bindings": await self._page_bindings(),
            "health_snapshot": await self._page_health_snapshot(),
        }
        return _json_response(data)

    async def page_approval_approve(self, approval_id: str):
        aid = str(approval_id or "").strip().upper()
        if not aid:
            return _error_response("missing approval_id", status_code=400)
        record = await claim_approval(self, aid)
        if not record:
            return _error_response("approval not found or expired", status_code=404)
        result = await self._dispatch_approved_action(record["action"], record["params"])
        logger.info("Dashboard approved ncqq approval %s by %s", aid, _page_username())
        return _json_response(
            {
                "approval_id": aid,
                "status": "approved",
                "description": record.get("description", ""),
                "result": result,
            }
        )

    async def page_approval_reject(self, approval_id: str):
        aid = str(approval_id or "").strip().upper()
        if not aid:
            return _error_response("missing approval_id", status_code=400)
        payload = await _request_json()
        reason = str(payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
        record = await claim_approval(self, aid)
        if not record:
            return _error_response("approval not found or expired", status_code=404)
        logger.info("Dashboard rejected ncqq approval %s by %s", aid, _page_username())
        return _json_response(
            {
                "approval_id": aid,
                "status": "rejected",
                "description": record.get("description", ""),
                "reason": reason,
            }
        )

    async def _page_manager_summary(self, manager_id: str) -> dict[str, Any]:
        profile = self.clients.profile(manager_id)
        health_task = _manager_get(self, "/api/health", manager_id)
        bots_task = _manager_get(self, "/api/bots", manager_id)
        containers_task = _list_containers(self, manager_id)
        health, bots, containers = await asyncio.gather(
            health_task,
            bots_task,
            containers_task,
            return_exceptions=True,
        )
        bot_lookup = _page_bot_lookup(bots)
        return {
            "id": manager_id,
            "name": profile.name,
            "url": profile.manager_url,
            "is_default": manager_id == self.default_manager_id(),
            "health": _page_health(health),
            "bots": _page_bots(bots),
            "instances": _page_instances(containers, bot_lookup, profile.manager_url),
        }

    async def _page_approvals(self) -> list[dict[str, Any]]:
        now = time.time()
        items: list[dict[str, Any]] = []
        for record in await list_approvals(self):
            params = record.get("params") if isinstance(record.get("params"), dict) else {}
            items.append(
                {
                    "approval_id": str(record.get("approval_id") or ""),
                    "action": str(record.get("action") or ""),
                    "description": str(record.get("description") or ""),
                    "requester_qq": str(record.get("requester_qq") or ""),
                    "group_id": str(record.get("group_id") or ""),
                    "created_at": float(record.get("created_at") or 0),
                    "age_seconds": max(0, int(now - float(record.get("created_at") or 0))),
                    "manager_id": str(params.get("manager_id") or ""),
                    "instance_name": str(params.get("instance_name") or ""),
                    "backend_alias": str(params.get("backend_alias") or params.get("alias") or ""),
                }
            )
        return items

    async def _page_bindings(self) -> list[dict[str, Any]]:
        mapping = await self.get_user_mapping()
        if not isinstance(mapping, dict):
            return []
        items: list[dict[str, Any]] = []
        for qq, data in sorted(mapping.items(), key=lambda pair: str(pair[0])):
            if not isinstance(data, dict):
                continue
            instances = data.get("instances") if isinstance(data.get("instances"), list) else []
            items.append(
                {
                    "qq": str(qq),
                    "nickname": str(data.get("nickname") or ""),
                    "instances": [str(item) for item in instances],
                }
            )
        return items

    async def _page_health_snapshot(self) -> list[dict[str, Any]]:
        snapshot = await self.get_kv_data("health_snapshot", {})
        if not isinstance(snapshot, dict):
            return []
        items: list[dict[str, Any]] = []
        for ref, online in sorted(snapshot.items(), key=lambda pair: str(pair[0])):
            text = str(ref)
            if "/" in text:
                manager_id, instance_name = text.split("/", 1)
            else:
                manager_id, instance_name = self.default_manager_id(), text
            items.append(
                {
                    "ref": text,
                    "manager_id": manager_id,
                    "instance_name": instance_name,
                    "online": bool(online),
                }
            )
        return items


def _page_username() -> str:
    return str(getattr(g, "username", "") or "-")


async def _request_json() -> dict[str, Any]:
    try:
        payload = await request.get_json(silent=True)
    except TypeError:
        payload = await request.get_json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _json_response(data: dict[str, Any], status_code: int = 200):
    response = jsonify(data)
    response.status_code = status_code
    return response


def _error_response(message: str, status_code: int = 400):
    return _json_response({"status": "error", "message": message}, status_code=status_code)


def _page_int_config(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _page_health(result: Any) -> dict[str, Any]:
    if isinstance(result, Exception):
        return {"ok": False, "status": "error", "error": str(result)}
    ok, payload = result
    if not ok or not isinstance(payload, dict):
        return {"ok": False, "status": "error", "error": str(payload)}
    state_engine = payload.get("state_engine") if isinstance(payload.get("state_engine"), dict) else {}
    reasons = payload.get("degraded_reasons") if isinstance(payload.get("degraded_reasons"), list) else []
    return {
        "ok": str(payload.get("status") or "").lower() in {"ok", "healthy", "running", "degraded"},
        "status": str(payload.get("status") or "-"),
        "docker": bool(payload.get("docker")),
        "async_docker": bool(payload.get("async_docker")),
        "state_engine": bool(state_engine.get("running")),
        "degraded_reasons": [str(item) for item in reasons],
        "uptime": payload.get("uptime"),
    }


def _page_bots(result: Any) -> dict[str, Any]:
    if isinstance(result, Exception):
        return {"ok": False, "total": 0, "online": 0, "error": str(result)}
    ok, payload = result
    if not ok or not isinstance(payload, list):
        return {"ok": False, "total": 0, "online": 0, "error": str(payload)}
    online = sum(1 for item in payload if isinstance(item, dict) and item.get("connected"))
    return {"ok": True, "total": len(payload), "online": online}


def _page_bot_lookup(result: Any) -> dict[str, dict[str, Any]]:
    if isinstance(result, Exception):
        return {}
    ok, payload = result
    if not ok or not isinstance(payload, list):
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        for key in (
            item.get("name"),
            item.get("container_name"),
            item.get("uin"),
            item.get("bot_uin"),
        ):
            text = str(key or "").strip().lstrip("/")
            if text and text not in lookup:
                lookup[text] = item
    return lookup


def _page_instances(
    result: Any,
    bots: dict[str, dict[str, Any]],
    manager_url: str,
) -> dict[str, Any]:
    if isinstance(result, Exception):
        return {"ok": False, "items": [], "error": str(result), "running": 0, "total": 0}
    ok, containers, error = result
    if not ok:
        return {"ok": False, "items": [], "error": error, "running": 0, "total": 0}
    items = [_page_instance(item, bots, manager_url) for item in containers]
    return {
        "ok": True,
        "items": items,
        "running": sum(1 for item in items if item["running"]),
        "online": sum(1 for item in items if item["bot_online"]),
        "total": len(items),
    }


def _page_instance(
    item: dict[str, Any],
    bots: dict[str, dict[str, Any]],
    manager_url: str,
) -> dict[str, Any]:
    name = _container_name(item) or "-"
    uin = str(item.get("bot_uin") or item.get("uin") or "").strip()
    bot = bots.get(name) or bots.get(uin) or {}
    avatar = str(item.get("bot_avatar") or bot.get("avatar") or bot.get("bot_avatar") or "").strip()
    return {
        "name": name,
        "display_name": str(
            item.get("bot_nickname")
            or item.get("nickname")
            or bot.get("nickname")
            or bot.get("name")
            or name
        ),
        "status": str(item.get("status") or item.get("state") or "-"),
        "running": _is_running(item),
        "bot_online": bool(item.get("bot_online") or bot.get("connected")),
        "uin": uin or str(bot.get("uin") or bot.get("bot_uin") or ""),
        "avatar": _page_absolute_url(avatar, manager_url),
        "login_stage": str(item.get("login_stage") or ""),
        "login_method": str(item.get("login_method") or ""),
        "heartbeat_ts": item.get("bot_heartbeat_ts") or bot.get("last_seen"),
        "image": str(item.get("image") or ""),
    }


def _page_absolute_url(value: str, base_url: str) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://", "data:")):
        return value
    if value.startswith("/") and base_url:
        return base_url.rstrip("/") + value
    return value
