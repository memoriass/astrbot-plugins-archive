from __future__ import annotations

from typing import Any

from quart import request

from .store import CONTRACT_VERSION


async def json_payload() -> dict[str, Any]:
    if not request.content_length:
        return {}
    payload = await request.get_json(force=True)
    return payload if isinstance(payload, dict) else {}


async def request_values() -> dict[str, Any]:
    if request.method == "POST":
        return await json_payload()
    return {
        "query": request.args.get("query", ""),
        "scope_id": request.args.get("scope_id", ""),
        "scope_ids": request.args.get("scope_ids", ""),
        "shared_scope_ids": request.args.get("shared_scope_ids", ""),
        "unified_msg_origin": request.args.get("unified_msg_origin", ""),
        "actor_id": request.args.get("actor_id", ""),
        "role": request.args.get("role", ""),
        "event_type": request.args.get("event_type", ""),
        "limit": request.args.get("limit", 10),
    }


def contract_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "contract_version_mismatch",
        "contract_version": CONTRACT_VERSION,
    }
