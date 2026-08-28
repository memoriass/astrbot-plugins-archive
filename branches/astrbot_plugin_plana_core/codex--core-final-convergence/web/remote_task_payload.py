from __future__ import annotations

from time import time
from typing import Any


ACTIVE_STATUSES = {"queued", "submitted", "running", "cancelling"}


def build_remote_task_web_payload(
    stats: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    current = int(time()) if now is None else int(now)
    presented = [_item(item, current) for item in items if isinstance(item, dict)]
    executor = _executor_summary(presented)
    return {
        "stats": stats,
        "items": items,
        "summary": {
            "total": len(presented),
            "active": sum(item["display"]["category"] == "active" for item in presented),
            "stale": sum(bool(item["display"]["stale"]) for item in presented),
            "completed": sum(item["display"]["category"] == "completed" for item in presented),
            "failed": sum(item["display"]["category"] == "failed" for item in presented),
            "executor": executor,
        },
        "display_items": presented,
    }


def _item(item: dict[str, Any], now: int) -> dict[str, Any]:
    status = str(item.get("status") or "unknown").lower()
    lane = str(item.get("lane") or "interactive").lower()
    updated_at = _integer(item.get("updated_at"))
    created_at = _integer(item.get("created_at"))
    wait_seconds = max(0, now - (updated_at or created_at or now))
    threshold = 3600 if lane == "long" else 600
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    execution_state = (
        item.get("execution_state")
        if isinstance(item.get("execution_state"), dict)
        else {}
    )
    heartbeat_at = _integer(execution_state.get("heartbeat_at"))
    lease_expires_at = _integer(execution_state.get("lease_expires_at"))
    lease_expired = bool(
        status in ACTIVE_STATUSES and lease_expires_at and now > lease_expires_at
    )
    executor = _executor_details(item, payload, result, nested)
    stale = bool(
        status in ACTIVE_STATUSES
        and (lease_expired or (not lease_expires_at and wait_seconds > threshold))
    )
    service_ref = str(result.get("service_ref") or nested.get("service_ref") or "")
    capability = str(result.get("capability") or nested.get("capability") or "")
    raw_error = str(item.get("error") or result.get("error") or nested.get("error") or "")
    summary = str(
        result.get("result_summary")
        or nested.get("result_summary")
        or result.get("summary")
        or nested.get("summary")
        or ""
    )
    category = _category(status, stale)
    return {
        **item,
        "display": {
            "title": str(item.get("title") or "未命名远程任务")[:300],
            "status": "连接中断，等待恢复" if stale else _status_label(status),
            "category": category,
            "tone": "danger" if stale or category == "failed" else "success" if category == "completed" else "warn",
            "lane": "长任务" if lane == "long" else "交互任务",
            "wait_seconds": wait_seconds,
            "duration": _duration_label(wait_seconds),
            "stale": stale,
            "service": _service_label(service_ref, executor["executor"]),
            "capability": _capability_label(capability),
            "result": _result_label(summary, status, raw_error, executor["executor"]),
            "error": _error_label(raw_error, executor["executor"]),
            "next_action": _next_action(status, stale, raw_error),
            "can_cancel": status in ACTIVE_STATUSES,
            "connection_state": "disconnected" if stale else "connected" if heartbeat_at else "unknown",
            "attempt_id": str(execution_state.get("attempt_id") or "")[:200],
            "attempt_no": _integer(execution_state.get("attempt_no")),
            "event_seq": _integer(execution_state.get("event_seq")),
            "heartbeat_at": heartbeat_at,
            "lease_expires_at": lease_expires_at,
            "cancel_requested_at": _integer(execution_state.get("cancel_requested_at")),
            "cancel_acknowledged_at": _integer(execution_state.get("cancel_acknowledged_at")),
            "terminal_at": _integer(execution_state.get("terminal_at")),
            "cancellation_phase": _cancellation_phase(status, execution_state),
            "created_at": created_at,
            "updated_at": updated_at,
            **executor,
        },
        "technical": item,
    }


def _category(status: str, stale: bool) -> str:
    if status in {"failed", "cancel_failed"}:
        return "failed"
    if status in {"succeeded", "completed"}:
        return "completed"
    if stale or status in ACTIVE_STATUSES:
        return "active"
    return "other"


def _status_label(status: str) -> str:
    return {
        "queued": "等待提交",
        "submitted": "已提交",
        "running": "处理中",
        "cancelling": "正在取消",
        "cancelled": "已取消",
        "cancel_failed": "取消未成功",
        "succeeded": "已完成",
        "completed": "已完成",
        "failed": "失败",
    }.get(status, "状态未知")


def _cancellation_phase(status: str, execution_state: dict[str, Any]) -> str:
    if status == "cancelled" or execution_state.get("terminal_at") and status == "cancelled":
        return "terminated"
    if execution_state.get("cancel_acknowledged_at"):
        return "acknowledged"
    if execution_state.get("cancel_requested_at") or status == "cancelling":
        return "requested"
    return "none"


def _duration_label(seconds: int) -> str:
    if seconds < 60:
        return "刚刚更新"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前更新"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前更新"
    return f"{seconds // 86400} 天前更新"


def _service_label(value: str, executor_label: str) -> str:
    lowered = value.lower()
    if "qbittorrent" in lowered:
        return "qBittorrent"
    if "ani_rss" in lowered:
        return "ANI-RSS"
    if "ncqq" in lowered:
        return "NCQQ"
    if "komga" in lowered:
        return "Komga"
    return executor_label if not value or value == "codex" else value


def _capability_label(value: str) -> str:
    labels = {
        "qbittorrent.list_torrents": "查看下载任务",
        "qbittorrent.transfer_status": "查看传输状态",
        "qbittorrent.get_torrent": "查看任务详情",
        "qbittorrent.list_files": "查看任务文件",
        "ani_rss.list_subscriptions": "查看动漫订阅",
        "ani_rss.list_recent_updates": "查看最近更新",
        "ani_rss.get_subscription": "查看订阅详情",
        "ani_rss.search_title": "搜索动漫",
        "ani_rss.search_mikan": "搜索 Mikan 番剧",
        "ani_rss.list_mikan_groups": "查看 Mikan 字幕组",
        "ani_rss.list_anibt_groups": "查看 AniBT 字幕组",
        "ani_rss.list_anime_garden_groups": "查看 AnimeGarden 字幕组",
        "ncqq.list_instances": "查看机器人实例",
        "ncqq.get_manager_health": "检查 NCQQ Manager",
        "ncqq.list_backend_endpoints": "查看 NCQQ 后端",
        "ncqq.get_login_status": "查看登录状态",
        "komga.list_libraries": "查看漫画书库",
        "komga.search_series": "搜索漫画",
        "komga.list_recent": "查看最近更新",
        "codex.interactive": "Codex 交互任务",
        "codex.long_task": "Codex 长任务",
        "external_service_query": "外部服务查询",
        "browser_research": "浏览器研究",
    }
    return labels.get(value, "按请求处理" if not value else value)


def _result_label(summary: str, status: str, error: str, executor_label: str) -> str:
    if summary:
        if summary.startswith("qBittorrent torrents:"):
            return summary.replace("qBittorrent torrents:", "共找到").replace("; active in result:", " 个任务，其中活动任务") + " 个"
        return summary[:600]
    if status in {"succeeded", "completed"}:
        return "任务已完成，但没有提供额外摘要。"
    if error:
        return _error_label(error, executor_label)
    if status in ACTIVE_STATUSES:
        return f"任务仍在等待 {executor_label} 返回结果。"
    return "暂无可展示的结果。"


def _error_label(error: str, executor_label: str) -> str:
    if not error:
        return ""
    lowered = error.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return f"{executor_label} 在规定时间内没有返回结果。"
    if "401" in lowered or "unauthorized" in lowered:
        return "外部服务身份校验失败。"
    if "cancel" in lowered:
        return "取消请求未能正常完成。"
    return "远程执行未成功，请在技术详情中查看原因。"


def _next_action(status: str, stale: bool, error: str) -> str:
    if stale:
        return "建议确认任务是否仍需继续；如不需要，可取消该任务后重新发起。"
    if status in ACTIVE_STATUSES:
        return "可以稍后刷新；若等待时间异常，可取消后重新发起。"
    if status in {"failed", "cancel_failed"} or error:
        return "检查服务状态或缩小请求范围后重试。"
    return "无需处理。"


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _executor_details(
    item: dict[str, Any],
    payload: dict[str, Any],
    result: dict[str, Any],
    nested: dict[str, Any],
) -> dict[str, Any]:
    contract = str(payload.get("contract_version") or "").lower()
    task_type = str(payload.get("type") or "").lower()
    request_id = str(item.get("request_id") or payload.get("request_id") or "").lower()
    engine = str(payload.get("engine") or result.get("engine") or nested.get("engine") or "").lower()
    if not engine:
        if "codex" in contract or "codex" in task_type or request_id.startswith("codex-"):
            engine = "codex"
        else:
            engine = "unknown"
    label = "Codex CLI" if engine == "codex" else "未知执行端"
    default_profile = "codex_default" if engine == "codex" else "unknown"
    profile = str(payload.get("execution_profile") or result.get("execution_profile") or default_profile)
    revision = _integer(payload.get("profile_revision") or result.get("profile_revision") or 1)
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    workspace = str(
        result.get("workspace_identity")
        or nested.get("workspace_identity")
        or ""
    )[:240]
    authorization = str(constraints.get("authorization") or "")
    return {
        "executor_key": engine,
        "executor": label,
        "execution_profile": profile,
        "profile_revision": revision,
        "run_id": str(item.get("runner_run_id") or result.get("runner_run_id") or nested.get("runner_run_id") or "")[:180],
        "workspace": workspace,
        "approval": _approval_label(authorization),
    }


def _approval_label(value: str) -> str:
    return {
        "user_confirmed": "用户已确认",
        "approved": "已批准",
        "read_only": "只读自动执行",
    }.get(value.lower(), "由 Core 策略控制")


def _executor_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in items:
        key = str((item.get("display") or {}).get("executor_key") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "key": "codex",
        "label": "Codex CLI",
        "counts": counts,
    }
