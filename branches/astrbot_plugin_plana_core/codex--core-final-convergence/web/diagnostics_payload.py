from __future__ import annotations

from time import time
from typing import Any

from .inspectors import build_maintenance_status_payload


ISSUE_STATUSES = {"issue", "error", "failed", "offline", "unavailable", "stale"}
WARN_STATUSES = {"waiting", "warning", "warn", "restricted", "disabled", "unverified"}


def build_diagnostics_payload(
    runtime: Any,
    resources: dict[str, Any],
) -> dict[str, Any]:
    """Build a read-only operator snapshot from runtime-owned evidence."""

    debug = runtime.debug_status_payload()
    maintenance = build_maintenance_status_payload(runtime)
    services = [item for item in resources.get("resources", []) if isinstance(item, dict)]
    remote = debug.get("remote_task_runs") if isinstance(debug.get("remote_task_runs"), dict) else {}
    audit = runtime.memory_storage.audit.recent(12)
    service_rows = [_service_row(item) for item in services]
    issue_rows = [item for item in service_rows if item["tone"] in {"danger", "warn"}]
    validation = maintenance.get("validation") if isinstance(maintenance.get("validation"), dict) else {}
    validation_status = str(validation.get("status") or "unknown").lower()
    stale_remote = _integer(remote.get("stale"))
    failed_remote = _integer(remote.get("failed")) + _integer(remote.get("cancel_failed"))

    findings: list[dict[str, Any]] = []
    findings.extend(issue_rows)
    if validation_status not in {"green", "ok", "healthy"}:
        findings.append(
            _finding(
                "数据健康检查",
                "维护检查未处于完全正常状态。",
                "danger" if validation_status in ISSUE_STATUSES | {"red"} else "warn",
                "settings",
                "maintenance",
            )
        )
    if stale_remote:
        findings.append(
            _finding(
                "Codex 任务长时间未更新",
                f"发现 {stale_remote} 项需要核实的远程任务。",
                "danger",
                "resources",
                "remote",
            )
        )

    issue_count = sum(1 for item in findings if item["tone"] == "danger")
    warning_count = sum(1 for item in findings if item["tone"] == "warn")
    overall = "issue" if issue_count else "attention" if warning_count else "healthy"
    return {
        "generated_at": int(time()),
        "overall": {
            "status": overall,
            "issue_count": issue_count,
            "warning_count": warning_count,
            "service_count": len(service_rows),
        },
        "runtime": {
            "build": dict(getattr(runtime, "build_info", {})),
            "enabled": bool(getattr(runtime, "enabled", False)),
            "mode": str(debug.get("mode") or "unknown"),
            "jobs": debug.get("jobs") if isinstance(debug.get("jobs"), dict) else {},
        },
        "services": service_rows,
        "governance": {
            "domain_plugins": len(getattr(runtime, "domain_plugins", ()) or ()),
            "remote_tasks": {
                "active": _integer(remote.get("active")),
                "completed": _integer(remote.get("completed")),
                "failed": failed_remote,
                "stale": stale_remote,
            },
        },
        "data_health": {
            "validation": validation,
            "tables": maintenance.get("tables") if isinstance(maintenance.get("tables"), dict) else {},
            "backups": len(maintenance.get("backups") or []),
            "last_maintenance": maintenance.get("memory_maintenance_last_run") or {},
        },
        "findings": findings[:12],
        "recent_audit": audit,
        "technical": {
            "resources": resources,
            "runtime": debug,
            "maintenance": maintenance,
        },
    }


def _service_row(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or "unknown").lower()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    error = str(metadata.get("health_error") or metadata.get("last_error") or "")[:240]
    tone = "danger" if status in ISSUE_STATUSES else "warn" if status in WARN_STATUSES else "success"
    return {
        "resource_id": str(item.get("resource_id") or ""),
        "service_ref": str(item.get("service_ref") or ""),
        "name": str(item.get("display_name") or item.get("resource_id") or "未命名服务"),
        "status": status,
        "tone": tone,
        "description": str(item.get("description") or ""),
        "error": error,
        "updated_at": item.get("updated_at") or _resource_timestamp(item),
    }


def _resource_timestamp(item: dict[str, Any]) -> int:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return _integer(metadata.get("checked_at") or metadata.get("updated_at"))


def _finding(title: str, text: str, tone: str, section: str, subview: str) -> dict[str, Any]:
    return {"title": title, "text": text, "tone": tone, "section": section, "subview": subview}


def _counts(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        result[value] = result.get(value, 0) + 1
    return result


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
