"""Instance, login, lifecycle, backend, and delete workflow runners."""

from __future__ import annotations

from typing import Any, AsyncIterator

from astrbot.api.all import AstrMessageEvent

from ..core.approval import create_approval
from ..core.interaction import do_check_login_status
from ..core.monitoring import do_confirm_instance_action, do_get_radar_endpoints
from .access import (
    _assign_instance_to_user,
    _ensure_instance_access,
    _list_backend_endpoints,
    _resolve_backend_alias,
    _resolve_bind_qq,
    _resolve_target,
)
from .common import _find_container, _is_running, _list_containers
from .formatters import (
    _format_backend_aliases,
    _format_container_brief,
    _format_login_status,
)
from .models import WorkflowRequest, _LIFECYCLE_ACTIONS
from .parsing import _first_text, _get_bool, _normalize_action

async def _run_backend_connect(
    plugin: Any,
    event: AstrMessageEvent,
    manager_id: str,
    instance_name: str,
    backend_alias: str,
) -> AsyncIterator[Any]:
    resolved_alias, error = await _resolve_backend_alias(plugin, backend_alias, manager_id)
    if error:
        yield event.plain_result(error)
        return
    async for item in plugin.ncqq_backend(
        event,
        action="inject",
        alias=resolved_alias,
        instance_names=instance_name,
        manager_id=manager_id,
    ):
        yield item


async def _run_create_instance(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    ok, instance_name = await _resolve_target(plugin, event, request, allow_single_bound=False)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("实例创建流程需要明确新实例名。")
        return
    manager_id = request.manager_id
    client = plugin.client_for_manager(manager_id)

    backend_alias = _first_text(request.params, "backend_alias", "backend", "backend_name", "alias", "endpoint")
    need_qrcode = _get_bool(request.params, "qrcode", "need_qrcode", default=True)
    auto_start = _get_bool(request.params, "auto_start", "start", default=True)
    bind_qq = _resolve_bind_qq(plugin, event, request)
    nickname = _first_text(request.params, "nickname", "owner_name")

    resolved_backend_alias = ""
    if backend_alias:
        resolved_backend_alias, error = await _resolve_backend_alias(plugin, backend_alias, manager_id)
        if error:
            yield event.plain_result(error)
            return

    list_ok, containers, list_error = await _list_containers(plugin, manager_id)
    if not list_ok:
        yield event.plain_result(f"实例创建流程停止：无法读取容器列表。{list_error}")
        return

    current = _find_container(containers, instance_name)
    if current is not None:
        allowed, message = await _ensure_instance_access(plugin, event, instance_name, manager_id)
        if not allowed:
            yield event.plain_result(
                f"实例 {instance_name} 已存在，但当前账号没有操作权限。{message}"
            )
            return
        yield event.plain_result(
            "实例创建流程：实例已存在，跳过创建。\n"
            + _format_container_brief(current)
        )
    else:
        if not plugin.is_plugin_admin(event):
            params = {
                "instance_name": instance_name,
                "manager_id": manager_id,
                "backend_alias": resolved_backend_alias,
                "bind_qq": bind_qq or str(event.get_sender_id()),
                "nickname": nickname,
            }
            aid = await create_approval(
                plugin,
                action="create_instance",
                params=params,
                requester_qq=str(event.get_sender_id()),
                group_id=str(event.get_group_id() or ""),
                description=(
                    f"创建实例 {instance_name}"
                    + (f"，绑定 QQ {params['bind_qq']}" if params.get("bind_qq") else "")
                    + (f"，接入后端 {resolved_backend_alias}" if resolved_backend_alias else "")
                ),
            )
            yield plugin._approval_notice_single(
                event,
                "创建 ncqq 实例",
                aid,
                extra_text=(
                    "审批通过后会执行：创建实例、绑定用户、接入后端（如有）。"
                    "\n登录二维码需要实例启动后再次执行登录恢复流程。"
                ),
            )
            return

        yield event.plain_result("实例创建流程：未发现同名实例，开始创建。")
        async for item in plugin.ncqq_action(
            event,
            action="create",
            instance_names=instance_name,
            manager_id=manager_id,
        ):
            yield item

        confirmed, confirm_message = await do_confirm_instance_action(
            client,
            instance_name,
            ["create", "start"],
            timeout=20,
        )
        yield event.plain_result(confirm_message)

        list_ok, containers, list_error = await _list_containers(plugin, manager_id)
        current = _find_container(containers, instance_name) if list_ok else None
        if current is None:
            detail = "" if confirmed else "状态确认尚未完成。"
            yield event.plain_result(
                f"实例 {instance_name} 的创建请求已提交，但当前列表中尚未可见。"
                f"{detail}后端接入和二维码请稍后通过 connect/recover 流程继续。"
            )
            return

    if bind_qq and plugin.is_plugin_admin(event):
        bind_message = await _assign_instance_to_user(
            plugin, bind_qq, manager_id, instance_name, nickname
        )
        if bind_message:
            yield event.plain_result(bind_message)

    if auto_start and current is not None and not _is_running(current):
        yield event.plain_result("实例创建流程：实例存在但未运行，进入启动分支。")
        async for item in plugin.ncqq_action(
            event,
            action="start",
            instance_names=instance_name,
            manager_id=manager_id,
        ):
            yield item

    if resolved_backend_alias:
        yield event.plain_result(
            f"实例创建流程：进入后端接入分支，端点 {resolved_backend_alias}。"
        )
        async for item in _run_backend_connect(
            plugin,
            event,
            manager_id,
            instance_name,
            resolved_backend_alias,
        ):
            yield item

    payload = await do_check_login_status(client, instance_name)
    yield event.plain_result(_format_login_status(instance_name, payload))
    if need_qrcode and payload.get("status") != "error" and not payload.get("logged_in"):
        async for item in plugin.ncqq_qrcode(
            event, instance_name=instance_name, manager_id=manager_id
        ):
            yield item


async def _run_relogin_instance(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("登录恢复流程需要明确目标实例。")
        return
    manager_id = request.manager_id
    client = plugin.client_for_manager(manager_id)
    allowed, message = await _ensure_instance_access(plugin, event, instance_name, manager_id)
    if not allowed:
        yield event.plain_result(message)
        return

    if _get_bool(request.params, "restart_first", default=False):
        yield event.plain_result("登录恢复流程：按参数要求先重启实例。")
        async for item in plugin.ncqq_action(
            event,
            action="restart",
            instance_names=instance_name,
            manager_id=manager_id,
        ):
            yield item

    payload = await do_check_login_status(client, instance_name)
    yield event.plain_result(_format_login_status(instance_name, payload))
    if payload.get("status") == "error":
        return

    force_qrcode = _get_bool(request.params, "force_qrcode", default=False)
    need_qrcode = _get_bool(request.params, "qrcode", "need_qrcode", default=True)
    if payload.get("logged_in") and not force_qrcode:
        return
    if not need_qrcode and not force_qrcode:
        yield event.plain_result("当前未自动拉取二维码，因为 qrcode=false。")
        return
    async for item in plugin.ncqq_qrcode(
        event, instance_name=instance_name, manager_id=manager_id
    ):
        yield item


async def _run_control_instance(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    action = _normalize_action(_first_text(request.params, "action", "operation"))
    if action not in _LIFECYCLE_ACTIONS:
        yield event.plain_result("实例操作流程需要 action=start/stop/restart/pause/unpause/kill。")
        return

    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("实例操作流程需要明确目标实例。")
        return
    manager_id = request.manager_id
    client = plugin.client_for_manager(manager_id)
    allowed, message = await _ensure_instance_access(plugin, event, instance_name, manager_id)
    if not allowed:
        yield event.plain_result(message)
        return

    async for item in plugin.ncqq_action(
        event,
        action=action,
        instance_names=instance_name,
        manager_id=manager_id,
    ):
        yield item

    check_after = _get_bool(
        request.params,
        "check_after",
        "check_login",
        default=action in {"start", "restart", "unpause"},
    )
    if check_after:
        payload = await do_check_login_status(client, instance_name)
        yield event.plain_result(_format_login_status(instance_name, payload))


async def _run_connect_backend(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    backend_alias = _first_text(request.params, "backend_alias", "backend", "backend_name", "alias", "endpoint")
    manager_id = request.manager_id
    client = plugin.client_for_manager(manager_id)
    if not backend_alias:
        endpoints = await do_get_radar_endpoints(client)
        yield event.plain_result(
            "后端接入流程需要 backend_alias。当前可用：" + _format_backend_aliases(endpoints)
        )
        return

    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("后端接入流程需要明确目标实例。")
        return
    manager_id = request.manager_id
    allowed, message = await _ensure_instance_access(plugin, event, instance_name, manager_id)
    if not allowed:
        yield event.plain_result(message)
        return

    resolved_alias, error = await _resolve_backend_alias(plugin, backend_alias, manager_id)
    if error:
        yield event.plain_result(error)
        return
    async for item in _run_backend_connect(plugin, event, manager_id, instance_name, resolved_alias):
        yield item


async def _run_check_instance(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("实例诊断流程需要明确目标实例。")
        return
    manager_id = request.manager_id
    client = plugin.client_for_manager(manager_id)

    list_ok, containers, list_error = await _list_containers(plugin, manager_id)
    if not list_ok:
        yield event.plain_result(f"实例诊断流程停止：无法读取容器列表。{list_error}")
        return
    current = _find_container(containers, instance_name)
    if current is None:
        yield event.plain_result(f"实例 {instance_name} 不存在，停止诊断。")
        return

    yield event.plain_result("实例诊断流程：\n" + _format_container_brief(current))
    payload = await do_check_login_status(client, instance_name)
    yield event.plain_result(_format_login_status(instance_name, payload))
    async for item in plugin.ncqq_query(
        event, query="monitor", instance_names=instance_name, manager_id=manager_id
    ):
        yield item
    async for item in plugin.ncqq_query(
        event, query="logs", instance_names=instance_name, manager_id=manager_id
    ):
        yield item

    file_name = _first_text(request.params, "file_name", "config_file")
    path = _first_text(request.params, "path")
    if path:
        async for item in plugin.ncqq_query(
            event,
            query="files",
            instance_names=instance_name,
            manager_id=manager_id,
            path=path,
        ):
            yield item
    if file_name:
        async for item in plugin.ncqq_query(
            event,
            query="config",
            instance_names=instance_name,
            manager_id=manager_id,
            file_name=file_name,
        ):
            yield item

async def _run_delete_instance(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    ok, instance_name = await _resolve_target(plugin, event, request)
    if not ok:
        yield event.plain_result(instance_name)
        return
    if not instance_name:
        yield event.plain_result("实例销毁流程需要明确目标实例。")
        return
    manager_id = request.manager_id
    allowed, message = await _ensure_instance_access(plugin, event, instance_name, manager_id)
    if not allowed:
        yield event.plain_result(message)
        return
    if not _get_bool(request.params, "confirm", "confirmed", default=False):
        yield event.plain_result(
            "实例销毁流程需要显式确认：params.confirm=true。"
            "如需同时删除数据目录，设置 params.delete_data=true。"
        )
        return
    delete_data = _get_bool(request.params, "delete_data", "clean_data", default=False)
    async for item in plugin.ncqq_action(
        event,
        action="delete",
        instance_names=instance_name,
        delete_data=delete_data,
        manager_id=manager_id,
    ):
        yield item
