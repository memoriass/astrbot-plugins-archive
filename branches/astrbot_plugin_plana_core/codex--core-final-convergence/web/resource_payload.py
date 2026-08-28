from __future__ import annotations

import asyncio
import importlib
from time import time
from typing import Any
from urllib.parse import urlsplit

import aiohttp


async def build_resource_web_payload(runtime: Any, *, limit: int = 80) -> dict[str, Any]:
    """Merge persisted governance resources with read-only operational devices."""

    payload = runtime.resource_storage.inspection_snapshot(limit=limit)
    operational = await _operational_inventory(runtime)
    payload["services"] = _merge_by_key(payload.get("services"), operational["services"], "service_ref")
    payload["resources"] = _merge_by_key(payload.get("resources"), operational["resources"], "resource_id")
    payload["operational"] = {
        "generated_at": int(time()),
        "status": _aggregate_status(operational["resources"]),
        "source": "runtime_read_only",
    }
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    payload["counts"] = {
        **counts,
        "display_services": len(payload["services"]),
        "display_resources": len(payload["resources"]),
        "operational_services": len(operational["services"]),
        "operational_resources": len(operational["resources"]),
    }
    return payload


async def _operational_inventory(runtime: Any) -> dict[str, list[dict[str, Any]]]:
    bridge = _active_bridge()
    relay = getattr(bridge, "codex_relay", None)
    bridge_status = _status(bridge)
    relay_status = _status(relay)
    runner_url = str(getattr(relay, "runner_url", "") or "").strip()
    gateway_url = str(runtime.config.get("assistant_service_gateway_url") or "").strip()
    runner_health, gateway_health = await asyncio.gather(
        _probe_json(_health_url(runner_url)),
        _probe_json(_health_url(gateway_url)),
    )
    warehouse_status = _call(getattr(runtime, "memory_warehouse_client", None), "local_status")
    core_status = "active" if bool(getattr(runtime, "enabled", False)) else "disabled"
    bridge_live = bool(bridge and bridge_status.get("enabled", True))
    relay_live = bool(relay_status.get("enabled") and relay_status.get("configured"))
    runner_live = bool(runner_health.get("ok"))
    gateway_enabled = bool(runtime.config.get("assistant_service_gateway_enabled", True))
    gateway_live = bool(gateway_health.get("ok"))
    warehouse_enabled = bool(warehouse_status.get("enabled"))
    warehouse_live = bool(warehouse_enabled and not warehouse_status.get("last_error"))

    services = [
        _service("plana.core", "control_plane", "local", core_status, "runtime"),
        _service("plana.bridge", "bridge_gateway", "local", _live_status(bridge_live), "runtime"),
        _service("codex.runner", "remote_executor", "remote_runner", _live_status(runner_live, relay_live), "bridge"),
        _service("adapter.gateway", "adapter_gateway", "remote_service", _live_status(gateway_live, gateway_enabled), "runtime"),
        _service("plana.memory_warehouse", "memory_warehouse", "local", _live_status(warehouse_live, warehouse_enabled), "runtime"),
    ]
    resources = [
        _resource("device:plana-core", "plana.core", "server", "Plana Core · 201", core_status,
                  "Core 治理、确认、审计与工作流执行入口。",
                  {"role": "control_plane", "build": dict(getattr(runtime, "build_info", {}))}),
        _resource("service:plana-bridge", "plana.bridge", "service", "Bridge Gateway · 201",
                  _live_status(bridge_live), "连接 Core、Codex Runner 与内部适配服务。",
                  {"role": "relay", "status": bridge_status, "proactive_loop": _status(getattr(bridge, "proactive_loop", None))}),
        _resource("device:codex-runner", "codex.runner", "remote", f"Codex Runner · {_host(runner_url, '202')}",
                  _live_status(runner_live, relay_live), "隔离执行长任务、工具任务和受控 Codex proposal。",
                  {"role": "remote_executor", "engine": runner_health.get("engine") or "codex",
                   "model": runner_health.get("model") or "", "fallback_models": runner_health.get("fallback_models") or [],
                   "workers": runner_health.get("workers") or {}, "lanes": runner_health.get("lanes") or {},
                   "task_skill_contract": runner_health.get("task_skill_contract") or "",
                   "candidate_output_schema": runner_health.get("candidate_output_schema") or "",
                   "relay": relay_status, "health_error": runner_health.get("error") or ""}),
        _resource("service:adapter-gateway", "adapter.gateway", "service", f"Adapter Gateway · {_host(gateway_url, '202')}",
                  _live_status(gateway_live, gateway_enabled), "为 ANI-RSS、NCQQ、qBittorrent 等提供受控只读访问。",
                  {"role": "service_adapter", "health": gateway_health, "configured": bool(gateway_url)}),
        _resource("service:memory-warehouse", "plana.memory_warehouse", "storage", "Memory Warehouse · 201",
                  _live_status(warehouse_live, warehouse_enabled), "保存受控长期记忆副本和维护同步状态。",
                  {"role": "memory_storage", "status": warehouse_status}),
    ]
    return {"services": services, "resources": resources}


async def _probe_json(url: str) -> dict[str, Any]:
    if not url:
        return {"ok": False, "error": "not_configured"}
    try:
        timeout = aiohttp.ClientTimeout(total=2.5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"Accept": "application/json"}) as response:
                data = await response.json(content_type=None)
                if isinstance(data, dict):
                    data = dict(data)
                    data["ok"] = bool(response.status < 400 and data.get("ok", True))
                    return data
                return {"ok": response.status < 400, "status_code": response.status}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return {"ok": False, "error": str(exc)[:160] or exc.__class__.__name__}


def _active_bridge() -> Any:
    for module_name in (
        "data.plugins.astrbot_plugin_plana_bridge_gateway.bridge.filters",
        "astrbot_plugin_plana_bridge_gateway.bridge.filters",
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        getter = getattr(module, "active_bridge_gateway", None)
        if callable(getter):
            bridge = getter()
            if bridge is not None:
                return bridge
    return None


def _health_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    return f"{parsed.scheme}://{parsed.netloc}/health" if parsed.scheme and parsed.netloc else ""


def _host(url: str, fallback: str) -> str:
    return str(urlsplit(str(url or "")).hostname or fallback)


def _status(target: Any) -> dict[str, Any]:
    return _call(target, "status")


def _call(target: Any, method: str) -> dict[str, Any]:
    callback = getattr(target, method, None)
    if not callable(callback):
        return {}
    try:
        value = callback()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160]}
    return value if isinstance(value, dict) else {}


def _service(ref: str, service_type: str, target: str, status: str, source: str) -> dict[str, Any]:
    return {"service_ref": ref, "service_type": service_type, "execution_target": target,
            "status": status, "source": source, "version": 1, "updated_at": int(time())}


def _resource(resource_id: str, service_ref: str, resource_type: str, display_name: str,
              status: str, description: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"resource_id": resource_id, "service_ref": service_ref, "resource_type": resource_type,
            "display_name": display_name, "status": status, "source": "runtime", "version": 1,
            "updated_at": int(time()), "description": description, "metadata": metadata, "read_only": True}


def _live_status(live: bool, configured: bool = True) -> str:
    return "disabled" if not configured else "active" if live else "issue"


def _merge_by_key(existing: Any, operational: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows = [dict(item) for item in existing or [] if isinstance(item, dict)]
    index = {str(item.get(key) or ""): position for position, item in enumerate(rows)}
    for item in operational:
        value = str(item.get(key) or "")
        if value in index:
            rows[index[value]] = {**rows[index[value]], **item}
        else:
            rows.append(item)
    return rows


def _aggregate_status(resources: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in resources}
    return "issue" if "issue" in statuses else "degraded" if "disabled" in statuses else "active"
