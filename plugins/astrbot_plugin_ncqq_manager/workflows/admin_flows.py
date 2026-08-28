"""Administrative, health, audit, resource, and config workflow runners."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from astrbot.api.all import AstrMessageEvent

from .access import _list_backend_endpoints, _resolve_target
from .common import _as_int, _list_containers, _manager_get, _result_payload
from .formatters import (
    _format_audit_operations,
    _format_backend_list,
    _format_bot_runtime,
    _format_check_botshepherd,
    _format_check_health,
    _format_check_manager,
    _format_recent_messages,
)
from .models import WorkflowRequest
from .parsing import _first_text, _get_bool

async def _run_check_health(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    manager_id = request.manager_id
    results = await asyncio.gather(
        _manager_get(plugin, "/api/health", manager_id),
        _manager_get(plugin, "/api/botshepherd/status", manager_id),
        _manager_get(plugin, "/api/botshepherd/activation", manager_id),
        _manager_get(plugin, "/api/botshepherd/bots/heartbeat", manager_id),
        _manager_get(plugin, "/api/bots", manager_id),
        _list_containers(plugin, manager_id),
        _list_backend_endpoints(plugin, manager_id),
        return_exceptions=True,
    )

    manager_ok, manager_payload = _result_payload(results[0])
    bs_status_ok, bs_status = _result_payload(results[1])
    activation_ok, activation = _result_payload(results[2])
    heartbeat_ok, heartbeat = _result_payload(results[3])
    bots_ok, bots = _result_payload(results[4])

    if isinstance(results[5], Exception):
        containers_ok = False
        containers: list[dict[str, Any]] = []
        container_error = str(results[5])
    else:
        containers_ok, containers, container_error = results[5]

    if isinstance(results[6], Exception):
        endpoints_ok = False
        endpoints: list[dict[str, Any]] = []
        endpoint_error = str(results[6])
    else:
        endpoints_ok, endpoints, endpoint_error = results[6]

    details = _get_bool(request.params, "details", "detail", "verbose", default=False)
    yield event.plain_result(
        _format_check_health(
            manager_ok=manager_ok,
            manager_payload=manager_payload,
            botshepherd_status_ok=bs_status_ok,
            botshepherd_status=bs_status,
            activation_ok=activation_ok,
            activation=activation,
            heartbeat_ok=heartbeat_ok,
            heartbeat=heartbeat,
            bots_ok=bots_ok,
            bots=bots,
            containers_ok=bool(containers_ok),
            containers=containers if isinstance(containers, list) else [],
            container_error=str(container_error or ""),
            endpoints_ok=bool(endpoints_ok),
            endpoints=endpoints if isinstance(endpoints, list) else [],
            endpoint_error=str(endpoint_error or ""),
            details=details,
        )
    )


async def _run_check_manager(
    plugin: Any,
    event: AstrMessageEvent,
    manager_id: str = "",
) -> AsyncIterator[Any]:
    ok, payload = await _manager_get(plugin, "/api/health", manager_id)
    if not ok or not isinstance(payload, dict):
        yield event.plain_result(f"管理器健康检查失败：{payload}")
        return
    yield event.plain_result(_format_check_manager(payload))


async def _run_check_botshepherd(
    plugin: Any,
    event: AstrMessageEvent,
    manager_id: str = "",
) -> AsyncIterator[Any]:
    ok_status, status = await _manager_get(plugin, "/api/botshepherd/status", manager_id)
    ok_activation, activation = await _manager_get(plugin, "/api/botshepherd/activation", manager_id)
    ok_heartbeat, heartbeat = await _manager_get(
        plugin, "/api/botshepherd/bots/heartbeat", manager_id
    )
    if not ok_status or not isinstance(status, dict):
        yield event.plain_result(f"BotShepherd 状态读取失败：{status}")
        return
    yield event.plain_result(
        _format_check_botshepherd(
            status,
            activation if ok_activation and isinstance(activation, dict) else {},
            heartbeat if ok_heartbeat and isinstance(heartbeat, dict) else {},
        )
    )


async def _run_check_bot_runtime(
    plugin: Any,
    event: AstrMessageEvent,
    manager_id: str = "",
) -> AsyncIterator[Any]:
    ok, payload = await _manager_get(plugin, "/api/bots", manager_id)
    if not ok or not isinstance(payload, list):
        yield event.plain_result(f"Bot 运行态读取失败：{payload}")
        return
    yield event.plain_result(_format_bot_runtime(payload))


async def _run_read_bot_messages(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    target = _first_text(request.params, "bot", "bot_name") or request.target
    if not target:
        yield event.plain_result("read_bot_messages 需要目标 Bot/实例名。")
        return
    try:
        request.manager_id, target = plugin.split_instance_ref(target, request.manager_id)
    except KeyError:
        yield event.plain_result(f"未知 ncqq-manager 面板。可用：{', '.join(plugin.manager_ids())}")
        return
    limit = _as_int(request.params.get("limit"), default=20, maximum=50)
    ok, payload = await _manager_get(
        plugin, f"/api/bots/{target}/messages?limit={limit}", request.manager_id
    )
    if not ok or not isinstance(payload, dict):
        yield event.plain_result(f"最近消息读取失败：{payload}")
        return
    yield event.plain_result(_format_recent_messages(payload))


async def _run_audit_operations(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    limit = _as_int(request.params.get("limit"), default=10, maximum=50)
    ok, payload = await _manager_get(
        plugin, f"/api/operation_logs?limit={limit}", request.manager_id
    )
    if not ok or not isinstance(payload, dict):
        yield event.plain_result(f"操作审计读取失败：{payload}")
        return
    yield event.plain_result(_format_audit_operations(payload))


async def _run_inspect_resources(
    plugin: Any,
    event: AstrMessageEvent,
    manager_id: str = "",
) -> AsyncIterator[Any]:
    async for item in plugin.ncqq_query(event, query="assets", manager_id=manager_id):
        yield item


async def _run_read_instance_config(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("read_instance_config 需要目标实例。")
        return
    path = _first_text(request.params, "path")
    file_name = _first_text(request.params, "file_name", "config_file")
    async for item in plugin.ncqq_query(
        event,
        query="files",
        instance_names=instance_name,
        manager_id=request.manager_id,
        path=path,
    ):
        yield item
    if file_name:
        async for item in plugin.ncqq_query(
            event,
            query="config",
            instance_names=instance_name,
            manager_id=request.manager_id,
            file_name=file_name,
        ):
            yield item
