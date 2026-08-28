"""Text formatters for ncqq workflow responses."""

from __future__ import annotations

from typing import Any

from ..core.sanitization import sanitize_text
from .common import (
    _container_name,
    _fmt_bool,
    _fmt_ts,
    _health_bool,
    _health_state,
    _is_running,
)
from .models import COMPILED_WORKFLOWS

def _format_workflow_list() -> str:
    lines = ["可用 ncqq workflow："]
    for item in COMPILED_WORKFLOWS.values():
        if not item.user_visible:
            continue
        suffix = "（管理员）" if item.admin_only else ""
        lines.append(f"- {item.workflow}: {item.title}{suffix} - {item.purpose}")
    lines.append("每个 workflow 只覆盖一个能力方向；底层 API 调用作为流程内部步骤。")
    lines.append("聊天场景优先使用主流程；细分 workflow 仍可直接调用但默认不展示。")
    lines.append("查询类统一走 query；健康检查仅供内部代码、Plugin Pages 和定时监控使用。")
    return "\n".join(lines)

def _format_container_brief(item: dict[str, Any]) -> str:
    name = _container_name(item) or "-"
    state = item.get("status") or item.get("state") or "-"
    online = item.get("bot_online")
    uin = item.get("bot_uin") or item.get("uin") or "-"
    return f"{name}: container={state}, bot_online={_fmt_bool(online)}, uin={uin}"


def _format_login_status(instance_name: str, payload: dict[str, Any]) -> str:
    if payload.get("status") == "error":
        msg = str(payload.get("msg") or "登录状态检查失败。")
        return f"{instance_name}: {msg}"
    if payload.get("logged_in"):
        uin = str(payload.get("uin") or "")
        nickname = str(payload.get("nickname") or "")
        label = f"{nickname}({uin})" if uin else nickname or "已登录"
        return f"{instance_name}: 当前在线，账号 {label}。"
    return f"{instance_name}: 当前未登录，可以继续获取二维码。"


def _format_backend_list(endpoints: list[dict[str, Any]]) -> str:
    if not endpoints:
        return "当前没有配置任何后端端点。"
    lines = [f"后端端点（{len(endpoints)}）："]
    for item in endpoints:
        alias = sanitize_text(item.get("alias") or "-")
        url = sanitize_text(item.get("url") or "-")
        token_state = "yes" if item.get("token") else "no"
        lines.append(f"- {alias}: {url} token={token_state}")
    return "\n".join(lines)


def _format_backend_aliases(endpoints: list[dict[str, Any]]) -> str:
    aliases = [str(item.get("alias") or "").strip() for item in endpoints]
    aliases = [alias for alias in aliases if alias]
    return ", ".join(aliases[:20]) if aliases else "无"

def _format_check_health(
    *,
    manager_ok: bool,
    manager_payload: Any,
    botshepherd_status_ok: bool,
    botshepherd_status: Any,
    activation_ok: bool,
    activation: Any,
    heartbeat_ok: bool,
    heartbeat: Any,
    bots_ok: bool,
    bots: Any,
    containers_ok: bool,
    containers: list[dict[str, Any]],
    container_error: str,
    endpoints_ok: bool,
    endpoints: list[dict[str, Any]],
    endpoint_error: str,
    details: bool = False,
) -> str:
    lines = ["综合健康检查："]
    states: list[str] = []

    if manager_ok and isinstance(manager_payload, dict):
        reasons = manager_payload.get("degraded_reasons") or []
        state_engine = manager_payload.get("state_engine") or {}
        status_text = str(manager_payload.get("status") or "").lower()
        manager_warn = bool(reasons) or status_text == "degraded"
        manager_pass = (
            status_text in {"ok", "healthy", "running", "degraded"}
            and _health_bool(manager_payload.get("docker"), default=True)
            and _health_bool(manager_payload.get("async_docker"), default=True)
            and _health_bool(state_engine.get("running"), default=True)
        )
        states.append(_health_state(manager_pass, manager_warn))
        lines.append(
            "- manager: "
            f"{_health_state(manager_pass, manager_warn)} "
            f"status={manager_payload.get('status', '-')}, "
            f"docker={_fmt_bool(manager_payload.get('docker'))}, "
            f"state_engine={_fmt_bool(state_engine.get('running'))}, "
            f"degraded={', '.join(map(str, reasons)) if reasons else 'none'}"
        )
    else:
        states.append("FAIL")
        lines.append(f"- manager: FAIL {manager_payload}")

    if botshepherd_status_ok and isinstance(botshepherd_status, dict):
        activation_payload = activation.get("activation") if isinstance(activation, dict) else {}
        if not isinstance(activation_payload, dict):
            activation_payload = {}
        missing = activation_payload.get("missing_endpoints") or []
        bs_pass = (
            _health_bool(botshepherd_status.get("installed"))
            and _health_bool(botshepherd_status.get("initialized"))
            and _health_bool(botshepherd_status.get("running"))
        )
        bs_warn = bool(missing) or not activation_ok or not heartbeat_ok
        states.append(_health_state(bs_pass, bs_warn))
        lines.append(
            "- botshepherd: "
            f"{_health_state(bs_pass, bs_warn)} "
            f"running={_fmt_bool(botshepherd_status.get('running'))}, "
            f"activation={_fmt_bool(activation_payload.get('connected'))}, "
            f"missing={len(missing)}"
        )
    else:
        states.append("FAIL")
        lines.append(f"- botshepherd: FAIL {botshepherd_status}")

    if bots_ok and isinstance(bots, list):
        online = [item for item in bots if isinstance(item, dict) and item.get("connected")]
        total = len(bots)
        bot_warn = total > 0 and len(online) < total
        states.append(_health_state(True, bot_warn))
        lines.append(f"- bot_runtime: {_health_state(True, bot_warn)} online={len(online)}/{total}")
    else:
        states.append("WARN")
        lines.append(f"- bot_runtime: WARN {bots}")

    if containers_ok:
        running = [item for item in containers if _is_running(item)]
        stopped = [_container_name(item) for item in containers if not _is_running(item)]
        stopped = [name for name in stopped if name]
        inst_warn = bool(stopped)
        states.append(_health_state(True, inst_warn))
        tail = f", stopped={', '.join(stopped[:5])}" if stopped else ""
        lines.append(
            f"- instances: {_health_state(True, inst_warn)} running={len(running)}/{len(containers)}{tail}"
        )
    else:
        states.append("WARN")
        lines.append(f"- instances: WARN {container_error or '无法读取容器列表'}")

    if endpoints_ok:
        token_count = sum(1 for item in endpoints if isinstance(item, dict) and item.get("token"))
        endpoint_warn = not endpoints
        states.append(_health_state(True, endpoint_warn))
        lines.append(
            f"- backends: {_health_state(True, endpoint_warn)} endpoints={len(endpoints)}, token={token_count}/{len(endpoints)}"
        )
    else:
        states.append("WARN")
        lines.append(f"- backends: WARN {endpoint_error or '无法读取后端端点列表'}")

    if "FAIL" in states:
        overall = "FAIL"
    elif "WARN" in states:
        overall = "WARN"
    else:
        overall = "OK"
    lines.insert(1, f"- overall: {overall}")

    if details:
        detail_blocks: list[str] = []
        if manager_ok and isinstance(manager_payload, dict):
            detail_blocks.append(_format_check_manager(manager_payload))
        if botshepherd_status_ok and isinstance(botshepherd_status, dict):
            detail_blocks.append(
                _format_check_botshepherd(
                    botshepherd_status,
                    activation if activation_ok and isinstance(activation, dict) else {},
                    heartbeat if heartbeat_ok and isinstance(heartbeat, dict) else {},
                )
            )
        if bots_ok and isinstance(bots, list):
            detail_blocks.append(_format_bot_runtime(bots))
        if endpoints:
            detail_blocks.append(_format_backend_list(endpoints))
        if detail_blocks:
            lines.append("\n详细信息：")
            lines.append("\n\n".join(detail_blocks))

    return "\n".join(lines)

def _format_check_manager(payload: dict[str, Any]) -> str:
    botshepherd = payload.get("botshepherd") or {}
    state_engine = payload.get("state_engine") or {}
    metrics = payload.get("metrics") or {}
    reasons = payload.get("degraded_reasons") or []
    lines = [
        "管理器健康检查：",
        f"- status: {payload.get('status', '-')}",
        f"- degraded_reasons: {', '.join(map(str, reasons)) if reasons else 'none'}",
        f"- uptime: {payload.get('uptime', '-')}s",
        f"- docker: {_fmt_bool(payload.get('docker'))}",
        f"- async_docker: {_fmt_bool(payload.get('async_docker'))}",
        f"- state_engine: {_fmt_bool(state_engine.get('running'))}",
        f"- public_ws_connections: {payload.get('ws_public', '-')}",
        f"- operation_logger_buffer: {payload.get('operation_logger_buffer', '-')}",
        (
            "- botshepherd: "
            f"installed={_fmt_bool(botshepherd.get('installed'))}, "
            f"initialized={_fmt_bool(botshepherd.get('initialized'))}, "
            f"running={_fmt_bool(botshepherd.get('running'))}, "
            f"port={botshepherd.get('port', '-')}, pid={botshepherd.get('pid', '-')}"
        ),
    ]
    if isinstance(metrics, dict) and metrics:
        lines.append(f"- metrics_keys: {', '.join(list(metrics.keys())[:8])}")
    return "\n".join(lines)


def _format_check_botshepherd(
    status: dict[str, Any],
    activation: dict[str, Any],
    heartbeat: dict[str, Any],
) -> str:
    activation_payload = activation.get("activation") if isinstance(activation, dict) else {}
    if not isinstance(activation_payload, dict):
        activation_payload = {}
    bots = heartbeat.get("bots") if isinstance(heartbeat, dict) else {}
    bot_count = len(bots) if isinstance(bots, dict) else 0
    lines = [
        "BotShepherd 状态：",
        f"- installed: {_fmt_bool(status.get('installed'))}",
        f"- initialized: {_fmt_bool(status.get('initialized'))}",
        f"- running: {_fmt_bool(status.get('running'))}",
        f"- auto_start: {_fmt_bool(status.get('auto_start'))}",
        f"- port: {status.get('port', '-')}",
        f"- pid: {status.get('pid', '-')}",
        f"- webui_url: {sanitize_text(status.get('webui_url') or status.get('webui_port') or '-')}",
        (
            "- activation: "
            f"running={_fmt_bool(activation_payload.get('running'))}, "
            f"connected={_fmt_bool(activation_payload.get('connected'))}, "
            f"active={activation_payload.get('active_connections', '-')}/"
            f"{activation_payload.get('total_connections', '-')}, "
            f"missing={len(activation_payload.get('missing_endpoints') or [])}"
        ),
        f"- heartbeat_bots: {bot_count}",
    ]
    return "\n".join(lines)


def _format_bot_runtime(bots: list[dict[str, Any]]) -> str:
    if not bots:
        return "当前没有已知 Bot 连接记录。"
    online = [item for item in bots if item.get("connected")]
    lines = [f"Bot 运行态概览：{len(online)}/{len(bots)} online"]
    for item in bots[:20]:
        name = str(item.get("name") or "-")
        uin = str(item.get("uin") or "-")
        nickname = str(item.get("nickname") or "")
        label = f"{nickname}({uin})" if nickname and uin != "-" else uin
        lines.append(
            f"- {name}: connected={_fmt_bool(item.get('connected'))}, "
            f"account={label}, last_seen={_fmt_ts(item.get('last_seen'))}"
        )
    if len(bots) > 20:
        lines.append(f"... 还有 {len(bots) - 20} 个 Bot 未显示")
    return "\n".join(lines)


def _message_text(message: dict[str, Any]) -> str:
    raw = sanitize_text(message.get("raw_message") or message.get("message") or "")
    raw = " ".join(raw.split())
    return raw[:120] + ("..." if len(raw) > 120 else "")


def _format_recent_messages(payload: dict[str, Any]) -> str:
    messages = payload.get("messages") if isinstance(payload, dict) else []
    if not isinstance(messages, list) or not messages:
        return f"{payload.get('name', '-')}: 当前没有最近消息缓存。"
    name = str(payload.get("name") or "-")
    lines = [f"{name} 最近消息（{len(messages)} 条）："]
    for item in messages[:20]:
        if not isinstance(item, dict):
            continue
        msg_type = str(item.get("message_type") or "-")
        source = item.get("group_id") if msg_type == "group" else item.get("user_id")
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        sender_name = sender.get("card") or sender.get("nickname") or item.get("user_id") or "-"
        lines.append(
            f"- [{_fmt_ts(item.get('time'))}] {msg_type} {source} {sender_name}: {_message_text(item)}"
        )
    return "\n".join(lines)


def _format_audit_operations(payload: dict[str, Any]) -> str:
    items = (
        payload.get("items")
        or payload.get("logs")
        or payload.get("records")
        or payload.get("data")
        or []
    )
    if not isinstance(items, list) or not items:
        return "最近没有操作审计记录。"
    total = payload.get("total", len(items))
    lines = [f"操作审计摘要：显示 {len(items)} / total={total}"]
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        op_type = item.get("type") or item.get("operation_type") or item.get("event") or "-"
        operator = item.get("operator_name") or item.get("operator") or item.get("user") or "-"
        level = item.get("level") or "-"
        ts = item.get("created_at") or item.get("time") or item.get("timestamp")
        target = sanitize_text(
            item.get("container_name")
            or item.get("name")
            or item.get("target")
            or item.get("details")
            or ""
        )
        lines.append(f"- [{_fmt_ts(ts)}] {level} {op_type} by {operator} {target}")
    return "\n".join(lines)
