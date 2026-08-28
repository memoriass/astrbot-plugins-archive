from __future__ import annotations


async def request_json() -> dict:
    from quart import request

    data = await request.get_json()
    return data if isinstance(data, dict) else {}


def ok(data: dict | None = None) -> dict:
    return {"status": "ok", "data": data or {}}


def error(message: str) -> dict:
    return {"status": "error", "message": message}
