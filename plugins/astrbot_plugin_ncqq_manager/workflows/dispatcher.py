"""Public workflow dispatcher for ncqq manager.

This module keeps the stable imports used by main.py while implementation
lives in focused workflow modules.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from astrbot.api.all import AstrMessageEvent

from ..core.monitoring import do_get_radar_endpoints
from .admin_flows import (
    _run_audit_operations,
    _run_inspect_resources,
    _run_read_bot_messages,
    _run_read_instance_config,
)
from .formatters import _format_backend_list, _format_workflow_list
from .instance_flows import (
    _run_check_instance,
    _run_connect_backend,
    _run_control_instance,
    _run_create_instance,
    _run_delete_instance,
    _run_relogin_instance,
)
from .models import COMPILED_WORKFLOWS, WorkflowRequest
from .parsing import (
    _first_text,
    _normalize_approval_action,
    _normalize_action,
    _normalize_workflow,
    workflow_from_cli,
    workflow_from_tool,
)

__all__ = ["WorkflowRequest", "run_ncqq_workflow", "workflow_from_cli", "workflow_from_tool"]

_INSTANCE_INTENTS = {
    "create": "create_instance",
    "new": "create_instance",
    "创建": "create_instance",
    "开通": "create_instance",
    "recover": "relogin_instance",
    "relogin": "relogin_instance",
    "login": "relogin_instance",
    "qrcode": "relogin_instance",
    "重登": "relogin_instance",
    "登录": "relogin_instance",
    "扫码": "relogin_instance",
    "control": "control_instance",
    "operate": "control_instance",
    "操作": "control_instance",
    "控制": "control_instance",
    "connect_backend": "connect_backend",
    "connect": "connect_backend",
    "backend": "connect_backend",
    "接入": "connect_backend",
    "check": "check_instance",
    "diagnose": "check_instance",
    "inspect": "check_instance",
    "检测": "check_instance",
    "诊断": "check_instance",
    "list": "list_instances",
    "status": "list_instances",
    "instances": "list_instances",
    "列表": "list_instances",
    "delete": "delete_instance",
    "remove": "delete_instance",
    "destroy": "delete_instance",
    "删除": "delete_instance",
    "销毁": "delete_instance",
}

_QUERY_SCOPES = {
    "": "list_instances",
    "instances": "list_instances",
    "instance": "check_instance",
    "list": "list_instances",
    "status": "list_instances",
    "实例": "list_instances",
    "backends": "check_backends",
    "backend": "check_backends",
    "endpoints": "check_backends",
    "后端": "check_backends",
    "messages": "read_bot_messages",
    "message": "read_bot_messages",
    "消息": "read_bot_messages",
    "audit": "audit_operations",
    "operations": "audit_operations",
    "审计": "audit_operations",
    "resources": "inspect_resources",
    "assets": "inspect_resources",
    "资源": "inspect_resources",
    "config": "read_instance_config",
    "files": "read_instance_config",
    "配置": "read_instance_config",
    "文件": "read_instance_config",
}

_BACKEND_INTENTS = {
    "": "check_backends",
    "list": "check_backends",
    "check": "check_backends",
    "query": "check_backends",
    "查看": "check_backends",
    "列表": "check_backends",
    "connect": "connect_backend",
    "inject": "connect_backend",
    "add": "connect_backend",
    "接入": "connect_backend",
    "注入": "connect_backend",
}


def _route_main_workflow(request: WorkflowRequest) -> str:
    if request.workflow == "manage_instance":
        return _route_instance_workflow(request)
    if request.workflow == "query":
        return _route_query_workflow(request)
    if request.workflow == "manage_backend":
        return _route_backend_workflow(request)
    return ""


def _route_instance_workflow(request: WorkflowRequest) -> str:
    intent = _normalize_workflow(_first_text(request.params, "intent", "scope", "operation"))
    action = _normalize_action(_first_text(request.params, "action", "operation"))
    if action in {"start", "stop", "restart", "pause", "unpause", "kill"}:
        request.params["action"] = action
        request.workflow = "control_instance"
        return ""
    if not intent and _first_text(request.params, "backend_alias", "backend", "backend_name", "alias", "endpoint"):
        request.workflow = "connect_backend"
        return ""
    if not intent:
        request.workflow = "check_instance" if request.target else "list_instances"
        return ""
    routed = _INSTANCE_INTENTS.get(intent)
    if routed is None:
        return "实例主流程需要 intent=create/recover/control/connect/check/list/delete。"
    request.workflow = routed
    return ""


def _route_query_workflow(request: WorkflowRequest) -> str:
    scope = _normalize_workflow(_first_text(request.params, "scope", "intent", "type"))
    routed = _QUERY_SCOPES.get(scope)
    if routed is None:
        return "查询主流程需要 scope=instances/backends/instance/messages/audit/resources/config。"
    request.workflow = routed
    return ""


def _route_backend_workflow(request: WorkflowRequest) -> str:
    intent = _normalize_workflow(_first_text(request.params, "intent", "action", "operation"))
    routed = _BACKEND_INTENTS.get(intent)
    if routed is None:
        return "后端主流程需要 intent=list/check/connect。"
    request.workflow = routed
    return ""

async def run_ncqq_workflow(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
) -> AsyncIterator[Any]:
    request.workflow = _normalize_workflow(request.workflow)
    route_error = _route_main_workflow(request)
    if route_error:
        yield event.plain_result(route_error)
        return
    spec = COMPILED_WORKFLOWS.get(request.workflow)
    if spec is None:
        yield event.plain_result("未知 ncqq workflow。\n" + _format_workflow_list())
        return
    if str(request.manager_id or "").strip():
        try:
            request.manager_id = plugin.normalize_manager_id(request.manager_id)
        except KeyError:
            yield event.plain_result(
                f"未知 ncqq-manager 面板：{request.manager_id}。可用：{', '.join(plugin.manager_ids())}"
            )
            return

    if spec.admin_only and not plugin.is_plugin_admin(event):
        yield event.plain_result(f"{spec.title} 仅限 AstrBot 管理员使用。")
        return

    if request.workflow == "create_instance":
        async for item in _run_create_instance(plugin, event, request):
            yield item
        return

    if request.workflow == "relogin_instance":
        async for item in _run_relogin_instance(plugin, event, request):
            yield item
        return

    if request.workflow == "control_instance":
        async for item in _run_control_instance(plugin, event, request):
            yield item
        return

    if request.workflow == "connect_backend":
        async for item in _run_connect_backend(plugin, event, request):
            yield item
        return

    if request.workflow == "check_instance":
        async for item in _run_check_instance(plugin, event, request):
            yield item
        return

    if request.workflow == "list_instances":
        async for item in plugin.ncqq_query(
            event, query="instances", manager_id=request.manager_id
        ):
            yield item
        return

    if request.workflow == "check_backends":
        endpoints = await do_get_radar_endpoints(plugin.client_for_manager(request.manager_id))
        yield event.plain_result(_format_backend_list(endpoints))
        return

    if request.workflow == "read_bot_messages":
        async for item in _run_read_bot_messages(plugin, event, request):
            yield item
        return

    if request.workflow == "audit_operations":
        async for item in _run_audit_operations(plugin, event, request):
            yield item
        return

    if request.workflow == "inspect_resources":
        async for item in _run_inspect_resources(plugin, event, request.manager_id):
            yield item
        return

    if request.workflow == "read_instance_config":
        async for item in _run_read_instance_config(plugin, event, request):
            yield item
        return

    if request.workflow == "delete_instance":
        async for item in _run_delete_instance(plugin, event, request):
            yield item
        return

    if request.workflow == "review_approvals":
        action = _normalize_approval_action(
            _first_text(request.params, "action", "operation") or "list"
        )
        approval_id = (_first_text(request.params, "approval_id", "id") or request.target).upper()
        reason = _first_text(request.params, "reason")
        async for item in plugin.ncqq_approval(
            event,
            action=action,
            approval_id=approval_id,
            reason=reason,
        ):
            yield item
        return

    yield event.plain_result("workflow 已注册但尚未实现，请检查插件版本。")
