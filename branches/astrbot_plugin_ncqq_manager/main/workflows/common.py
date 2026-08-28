"""Shared low-level helpers used by workflow runners and formatters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

async def _manager_get(plugin: Any, endpoint: str, manager_id: str = "") -> tuple[bool, Any]:
    try:
        return True, await plugin.client_for_manager(manager_id).make_request("GET", endpoint)
    except Exception as exc:
        return False, str(exc)


async def _list_containers(plugin: Any, manager_id: str = "") -> tuple[bool, list[dict[str, Any]], str]:
    ok, payload = await _manager_get(plugin, "/api/containers", manager_id)
    if not ok:
        return False, [], str(payload)
    if isinstance(payload, dict):
        containers = payload.get("containers", [])
    elif isinstance(payload, list):
        containers = payload
    else:
        containers = []
    if not isinstance(containers, list):
        return False, [], "容器列表返回格式异常。"
    return True, [item for item in containers if isinstance(item, dict)], ""

def _container_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("container_name") or "").strip().lstrip("/")


def _find_container(containers: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    wanted = name.strip().lstrip("/")
    for item in containers:
        if _container_name(item) == wanted:
            return item
    return None


def _container_state(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("status") or item.get("state") or item.get("container_status") or "").lower()


def _is_running(item: dict[str, Any] | None) -> bool:
    state = _container_state(item)
    return state == "running" or state.startswith("up")

def _result_payload(result: Any) -> tuple[bool, Any]:
    if isinstance(result, Exception):
        return False, str(result)
    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[0]), result[1]
    return True, result


def _health_state(ok: bool, warn: bool = False) -> str:
    if not ok:
        return "FAIL"
    if warn:
        return "WARN"
    return "OK"


def _health_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ok", "healthy", "running", "up"}:
        return True
    if text in {"0", "false", "no", "fail", "error", "down", "stopped"}:
        return False
    return bool(value)

def _as_int(value: Any, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _fmt_bool(value: Any) -> str:
    return "yes" if _health_bool(value) else "no"


def _fmt_ts(value: Any) -> str:
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return "-"
    if ts <= 0:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
