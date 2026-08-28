"""Workflow request parsing for LLM tool calls and /ncqq commands."""

from __future__ import annotations

import json
from typing import Any

from .models import COMPILED_WORKFLOWS, WorkflowRequest, _ACTION_ALIASES, _APPROVAL_ACTION_ALIASES

def _canonical_key(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _split_words(value: str) -> list[str]:
    return [part for part in str(value or "").split() if part]


def _split_cli_args(value: str) -> tuple[list[str], dict[str, Any]]:
    parts = _split_words(value)
    params: dict[str, Any] = {}
    positional: list[str] = []
    for token in parts:
        if "=" not in token:
            positional.append(token)
            continue
        key, raw = token.split("=", 1)
        key = key.strip()
        if key:
            params[key] = raw.strip()
    return positional, params


def _normalize_workflow(value: str) -> str:
    return _canonical_key(value)


def _normalize_action(value: Any) -> str:
    return _ACTION_ALIASES.get(_canonical_key(str(value or "")), _canonical_key(str(value or "")))


def _normalize_approval_action(value: Any) -> str:
    return _APPROVAL_ACTION_ALIASES.get(
        _canonical_key(str(value or "")),
        _canonical_key(str(value or "")),
    )


def _parse_kv_words(value: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for token in _split_words(value):
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        key = key.strip()
        if key:
            payload[key] = raw.strip()
    return payload


def _parse_params(params: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(params, dict):
        return dict(params)
    if not params:
        return {}
    text = str(params).strip()
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        parsed = _parse_kv_words(text)
        if parsed:
            parsed["_raw"] = text
            return parsed
        return {"_raw": text}
    return payload if isinstance(payload, dict) else {}


def _first_text(params: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _manager_text(params: dict[str, Any]) -> str:
    return _first_text(params, "manager_id", "manager", "panel", "site")


def _get_bool(params: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key not in params:
            continue
        value = params.get(key)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "需要", "是"}:
            return True
        if text in {"0", "false", "no", "n", "off", "不", "否", "不需要"}:
            return False
    return default


def workflow_from_tool(
    workflow: str,
    target: str = "",
    params: str | dict[str, Any] | None = "",
) -> WorkflowRequest:
    """Build a workflow request from the LLM tool shape."""
    payload = _parse_params(params)
    selected = _normalize_workflow(workflow or str(payload.get("workflow") or ""))

    resolved_target = str(
        target
        or payload.get("target")
        or payload.get("instance_name")
        or payload.get("name")
        or ""
    ).strip()
    return WorkflowRequest(
        workflow=selected,
        target=resolved_target,
        manager_id=_manager_text(payload),
        params=payload,
        source="tool",
    )


def workflow_from_cli(sub: str, args: str = "") -> WorkflowRequest | None:
    """Build a workflow request from `/ncqq <flow> [args...]`."""
    workflow = _normalize_workflow(sub)
    if workflow not in COMPILED_WORKFLOWS:
        return None

    args = str(args or "").strip()
    parts, params = _split_cli_args(args)
    target = ""

    if workflow == "manage_instance":
        params["intent"] = parts[0] if parts else ""
        if params["intent"] in _ACTION_ALIASES:
            params["action"] = _normalize_action(params["intent"])
            target = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif _canonical_key(str(params["intent"])) in {"control", "operate", "操作", "控制"}:
            params["action"] = _normalize_action(parts[1] if len(parts) > 1 else "")
            target = " ".join(parts[2:]) if len(parts) > 2 else ""
        elif _canonical_key(str(params["intent"])) in {"connect", "backend", "接入"}:
            params["backend_alias"] = parts[1] if len(parts) > 1 else ""
            target = " ".join(parts[2:]) if len(parts) > 2 else ""
        else:
            target = " ".join(parts[1:]) if len(parts) > 1 else ""
    elif workflow == "query":
        params["scope"] = parts[0] if parts else ""
        target = parts[1] if len(parts) > 1 else ""
        scope_key = _canonical_key(str(params["scope"]))
        if scope_key in {"messages", "message", "消息"}:
            params["limit"] = parts[2] if len(parts) > 2 else "20"
        elif scope_key in {"audit", "operations", "审计"}:
            params["limit"] = parts[1] if len(parts) > 1 else "10"
            target = ""
        elif scope_key in {"config", "files", "配置", "文件"}:
            params["file_name"] = parts[2] if len(parts) > 2 else ""
            params["path"] = parts[3] if len(parts) > 3 else ""
    elif workflow == "manage_backend":
        params["intent"] = parts[0] if parts else "list"
        if _canonical_key(str(params["intent"])) in {"connect", "inject", "add", "接入", "注入"}:
            params["backend_alias"] = parts[1] if len(parts) > 1 else ""
            target = " ".join(parts[2:]) if len(parts) > 2 else ""
    elif workflow == "create_instance":
        target = parts[0] if parts else ""
        if len(parts) > 1:
            params["backend_alias"] = parts[1]
        params["qrcode"] = True
    elif workflow == "relogin_instance":
        target = " ".join(parts)
    elif workflow == "control_instance":
        params["action"] = _normalize_action(parts[0] if parts else "")
        target = " ".join(parts[1:]) if len(parts) > 1 else ""
    elif workflow == "connect_backend":
        params["backend_alias"] = parts[0] if parts else ""
        target = " ".join(parts[1:]) if len(parts) > 1 else ""
    elif workflow == "check_instance":
        target = parts[0] if parts else args
    elif workflow in {
        "list_instances",
        "check_backends",
        "inspect_resources",
    }:
        target = ""
    elif workflow == "read_bot_messages":
        target = parts[0] if parts else ""
        params["limit"] = parts[1] if len(parts) > 1 else "20"
    elif workflow == "audit_operations":
        target = ""
        params["limit"] = parts[0] if parts else "10"
    elif workflow == "read_instance_config":
        target = parts[0] if parts else ""
        params["file_name"] = parts[1] if len(parts) > 1 else ""
        params["path"] = parts[2] if len(parts) > 2 else ""
    elif workflow == "delete_instance":
        target = parts[0] if parts else ""
        lowered = {p.lower() for p in parts[1:]}
        params["confirm"] = bool(lowered & {"confirm", "yes", "true", "确认"})
        params["delete_data"] = bool(lowered & {"data", "clean", "all", "彻底", "数据"})
    elif workflow == "review_approvals":
        target = ""
        params["action"] = _normalize_approval_action(parts[0] if parts else "list")
        params["approval_id"] = parts[1].upper() if len(parts) > 1 else ""
        params["reason"] = " ".join(parts[2:]) if len(parts) > 2 else ""

    return WorkflowRequest(
        workflow=workflow,
        target=target,
        manager_id=_manager_text(params),
        params=params,
        source="cli",
    )
