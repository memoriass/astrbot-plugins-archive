"""Access control, target resolution, and backend lookup helpers."""

from __future__ import annotations

from typing import Any

from astrbot.api.all import AstrMessageEvent

from ..core.monitoring import do_get_radar_endpoints
from .common import _manager_get
from .formatters import _format_backend_aliases
from .models import WorkflowRequest
from .parsing import _get_bool

async def _resolve_target(
    plugin: Any,
    event: AstrMessageEvent,
    request: WorkflowRequest,
    *,
    allow_single_bound: bool = True,
) -> tuple[bool, str]:
    explicit_manager = bool(str(request.manager_id or "").strip())
    try:
        fallback_manager = plugin.normalize_manager_id(request.manager_id)
    except KeyError:
        return False, f"未知 ncqq-manager 面板：{request.manager_id}。可用：{', '.join(plugin.manager_ids())}"
    request.manager_id = fallback_manager

    target = str(
        request.target
        or request.params.get("target")
        or request.params.get("instance_name")
        or request.params.get("name")
        or ""
    ).strip()
    if target:
        try:
            request.manager_id, target = plugin.split_instance_ref(target, fallback_manager)
        except KeyError:
            return False, f"未知 ncqq-manager 面板。可用：{', '.join(plugin.manager_ids())}"
        return True, target
    if not allow_single_bound:
        return True, ""

    refs = await plugin.get_allowed_instance_refs(str(event.get_sender_id()))
    if explicit_manager:
        refs = [item for item in refs if item[0] == fallback_manager]
    bound = [instance_name for _, instance_name in refs]
    if len(bound) == 1:
        request.manager_id = refs[0][0]
        return True, bound[0]
    if len(bound) > 1:
        choices = ", ".join(f"{manager}/{name}" for manager, name in refs)
        return False, "你绑定了多个 ncqq 实例，请明确指定其中一个：" + choices
    return True, ""


async def _ensure_instance_access(
    plugin: Any,
    event: AstrMessageEvent,
    instance_name: str,
    manager_id: str = "",
) -> tuple[bool, str]:
    if plugin.is_plugin_admin(event):
        return True, ""
    manager_id = plugin.normalize_manager_id(manager_id)
    allowed = await plugin.get_allowed_instances(str(event.get_sender_id()), manager_id)
    if instance_name in allowed:
        return True, ""
    return False, f"实例 {manager_id}/{instance_name} 不在你的可操作范围内。"

async def _list_backend_endpoints(
    plugin: Any,
    manager_id: str = "",
) -> tuple[bool, list[dict[str, Any]], str]:
    ok, payload = await _manager_get(plugin, "/api/botshepherd/radar/endpoints", manager_id)
    if not ok:
        return False, [], str(payload)
    if isinstance(payload, dict):
        endpoints = payload.get("endpoints", [])
    elif isinstance(payload, list):
        endpoints = payload
    else:
        return False, [], "后端端点返回格式异常。"
    if not isinstance(endpoints, list):
        return False, [], "后端端点列表返回格式异常。"
    return True, [item for item in endpoints if isinstance(item, dict)], ""

async def _resolve_backend_alias(
    plugin: Any,
    alias: str,
    manager_id: str = "",
) -> tuple[str, str]:
    endpoints = await do_get_radar_endpoints(plugin.client_for_manager(manager_id))
    wanted = alias.strip().lower()
    if not wanted:
        return "", "请提供要接入的后端端点别名。当前可用：" + _format_backend_aliases(endpoints)

    exact = [
        item for item in endpoints
        if str(item.get("alias") or "").strip().lower() == wanted
    ]
    matches = exact or [
        item for item in endpoints
        if wanted in str(item.get("alias") or "").strip().lower()
    ]

    if not matches:
        return "", f"未找到包含 '{alias}' 的后端端点。当前可用：" + _format_backend_aliases(endpoints)
    if len(matches) > 1:
        names = ", ".join(str(item.get("alias") or "-") for item in matches[:10])
        return "", f"后端端点别名不唯一，请说得更精确。匹配到：{names}"
    return str(matches[0].get("alias") or alias), ""


def _resolve_bind_qq(plugin: Any, event: AstrMessageEvent, request: WorkflowRequest) -> str:
    explicit = ""
    for key in ("bind_qq", "qq_id", "user_id", "owner_qq", "bind_to_user"):
        value = request.params.get(key)
        if isinstance(value, bool):
            continue
        if value is not None and str(value).strip():
            explicit = str(value).strip()
            break
    if explicit:
        return explicit
    try:
        at_user = plugin.get_first_at_user_id(event)
    except Exception:
        at_user = None
    if at_user:
        return str(at_user)
    if _get_bool(request.params, "bind_to_sender", default=not plugin.is_plugin_admin(event)):
        return str(event.get_sender_id())
    return ""


async def _assign_instance_to_user(
    plugin: Any,
    qq_id: str,
    manager_id: str,
    instance_name: str,
    nickname: str = "",
) -> str:
    if not qq_id:
        return ""
    mapping = await plugin.get_user_mapping()
    if qq_id not in mapping:
        mapping[qq_id] = {"nickname": "", "instances": []}
    instances = mapping[qq_id].setdefault("instances", [])
    instance_ref = plugin.format_instance_ref(manager_id, instance_name)
    added = instance_ref not in instances
    if added:
        instances.append(instance_ref)
    if nickname:
        mapping[qq_id]["nickname"] = nickname
    await plugin.save_user_mapping(mapping)
    state = "已新增绑定" if added else "绑定已存在"
    nick_part = f"，昵称：{nickname}" if nickname else ""
    return f"{state}：QQ {qq_id} -> {instance_ref}{nick_part}。"
