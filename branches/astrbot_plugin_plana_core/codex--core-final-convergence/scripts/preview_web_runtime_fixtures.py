from __future__ import annotations

from typing import Any


def memory_scopes_payload(*, pending_feedback: int, open_gaps: int) -> dict[str, Any]:
    return {
        "summary": {"scopes": 1, "memories": 2},
        "items": [
            {
                "id": "global",
                "label": "本地预览",
                "kind": "other",
                "counts": {
                    "memories": 2,
                    "semantics": 1,
                    "pending_feedback": pending_feedback,
                    "open_gaps": open_gaps,
                },
            }
        ],
    }


def domains_payload() -> dict[str, Any]:
    items = [
        {
            "id": "ani_rss",
            "name": "ANI-RSS",
            "plugin_name": "astrbot_plugin_ani_rss",
            "owner": "astrbot_plugin_ani_rss",
            "profile": "ani_plugin",
            "tool_name": "ani_rss",
            "status": "active",
            "aliases": ["追番", "订阅"],
            "read_operations": ["list_subscriptions", "search_mikan"],
            "write_operations": ["add_mikan_subscription", "refresh_subscription"],
            "direct_dispatch": True,
            "confirmation_policy": "host_governed_plugin_executed",
        },
        {
            "id": "ncqq",
            "name": "NCQQ Manager",
            "plugin_name": "astrbot_plugin_ncqq_manager",
            "owner": "astrbot_plugin_ncqq_manager",
            "profile": "ncqq_plugin",
            "tool_name": "ncqq_manager",
            "status": "active",
            "aliases": ["QQ 实例", "机器人"],
            "read_operations": ["list_instances", "instance_status"],
            "write_operations": ["restart_instance", "create_instance"],
            "direct_dispatch": True,
            "confirmation_policy": "host_governed_plugin_executed",
        },
        {
            "id": "komga",
            "name": "Komga Manager",
            "plugin_name": "astrbot_plugin_komga_manager",
            "owner": "astrbot_plugin_komga_manager",
            "profile": "komga_plugin",
            "tool_name": "komga_manager",
            "status": "active",
            "aliases": ["漫画库", "书库"],
            "read_operations": ["komga.list_recent", "komga.search_series"],
            "write_operations": ["komga.scan_library"],
            "direct_dispatch": True,
            "confirmation_policy": "host_governed_plugin_executed",
        },
    ]
    return {
        "domain_harness": {
            "status": "active",
            "summary": {
                "active_plugins": len(items),
                "discovered": len(items),
                "direct_dispatch": len(items),
                "confirmation_governed": len(items),
            },
            "items": items,
            "errors": [],
        }
    }


def remote_tasks_payload(now: int) -> dict[str, Any]:
    return {
        "summary": {
            "executor": {
                "name": "Codex Runner",
                "label": "原生 Runner · 202",
                "active": 0,
                "completed": 4,
                "failed": 0,
                "stale": 0,
            }
        },
        "display_items": [
            {
                "request_id": "preview-codex-001",
                "status": "completed",
                "updated_at": now - 600,
                "display": {
                    "title": "分析 NCQQ 掉线日志",
                    "status": "completed",
                    "tone": "success",
                    "lane": "interactive",
                    "duration": "42 秒",
                    "stale": False,
                },
            }
        ],
        "technical": {"preview": True},
    }


def tasks_payload(now: int) -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "title": "复核领域操作提案",
            "content": "确认目标与影响范围后再执行。",
            "source": "assistant",
            "status": "pending",
            "created_at": now - 100,
        }
    ]


def proactive_payload(items: dict[int, dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, int] = {}
    for item in items.values():
        status = str(item.get("status") or "pending")
        stats[status] = stats.get(status, 0) + 1
    return {"tasks": list(items.values()), "stats": stats}
