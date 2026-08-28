from __future__ import annotations

import json
import time
from typing import Any


def _now() -> int:
    return int(time.time())


def _workflow_run(run_id: int = 1001, goal: str = "复核一个生成的工作流") -> dict[str, Any]:
    now = _now()
    policy = {
        "surface": "preview_web",
        "toolset_profile": "astrbot_local",
        "proposal_hash": "preview-proposal-hash",
        "capability_view_hash": "preview-capability-hash",
        "risk_reasons": [
            "write_step_requires_confirmation",
            "workflow_center_proposal_only",
        ],
        "notes": {
            "core_boundary": "review_confirm_execute",
            "workflow_center_boundary": "proposal_storage_only",
            "skill_center_boundary": "scan_approve_export",
        },
        "write_steps": [
            {
                "id": "wf.plan.persist",
                "uses": "workflow_center.create_draft",
                "side_effect": "persist_workflow_draft",
                "risk_level": "medium",
                "execution_backend": "workflow_center",
                "recommended_posture": "confirm_before_write",
            }
        ],
        "executor_trace": [
            {
                "step_id": "wf.plan.persist",
                "capability": "workflow_center.create_draft",
                "status": "waiting_confirm",
                "duration_ms": 0,
                "error_type": "",
            }
        ],
    }
    return {
        "id": run_id,
        "status": "waiting_confirm",
        "risk_level": "medium",
        "source": "preview_web",
        "goal": goal,
        "confirm_summary": "包含 1 个写入步骤，执行前需要 Core 审批。",
        "created_at": now - 300,
        "updated_at": now - 120,
        "proposal_hash": policy["proposal_hash"],
        "capability_view_hash": policy["capability_view_hash"],
        "context": {
            "surface": "preview_web",
            "toolset_profile": "astrbot_local",
        },
        "approval": {
            "status": "pending",
            "mode": "explicit",
            "expires_at": now + 3600,
            "decision": "",
            "decision_actor": "",
            "decision_source": "",
        },
        "draft": {
            "advisor_trace": [
                {"stage": "intent_shape", "status": "ok", "source": "core_rules"},
                {"stage": "risk_review", "status": "ok", "source": "advisor_model"},
            ]
        },
        "result": {
            "status": "waiting_confirm",
            "confirmation_required": True,
            "policy": policy,
            "steps": [
                {
                    "id": "wf.plan.persist",
                    "uses": "workflow_center.create_draft",
                    "status": "waiting_confirm",
                    "output": {"draft_id": "preview-draft-001"},
                }
            ],
        },
    }


RUNS: dict[int, dict[str, Any]] = {1001: _workflow_run()}
RECALL_GAPS: list[dict[str, Any]] = [
    {
        "id": 1,
        "scope_id": "global",
        "user_id": "preview-user",
        "query": "用户问到领域写操作确认边界时没有召回对应改造结论",
        "status": "open",
        "candidate_feedback_id": None,
        "candidate_at": None,
        "resolved_at": None,
        "resolved_by": "",
        "created_at": _now() - 1800,
    },
    {
        "id": 2,
        "scope_id": "global",
        "user_id": "preview-user",
        "query": "用户询问 LivingMemory canvas 展示逻辑时缺少 atom 评分解释",
        "status": "candidate",
        "candidate_feedback_id": 1,
        "candidate_at": _now() - 600,
        "resolved_at": None,
        "resolved_by": "",
        "created_at": _now() - 2400,
    },
]
FEEDBACK_QUEUE: list[dict[str, Any]] = [
    {
        "id": 1,
        "scope_id": "global",
        "user_id": "preview-user",
        "kind": "new_memory",
        "payload": {
            "content": "Plana Core 负责审查和确认，领域插件负责生成结构化操作提案。",
            "kind": "semantic_note",
        },
        "status": "pending",
        "created_at": _now() - 600,
    }
]
PROACTIVE: dict[int, dict[str, Any]] = {
    2001: {
        "id": 2001,
        "scope_id": "global",
        "user_id": "preview",
        "kind": "reminder",
        "payload": json.dumps({"title": "复盘", "message": "检查自然语言提醒解析结果"}, ensure_ascii=False),
        "status": "pending",
        "priority": 10,
        "scheduled_at": _now() - 60,
        "expires_at": _now() + 86400,
        "delivered_at": None,
        "created_at": _now() - 3600,
    },
    2002: {
        "id": 2002,
        "scope_id": "global",
        "user_id": "preview",
        "kind": "appointment",
        "payload": json.dumps({"title": "会议", "message": "明天 9 点提醒开会"}, ensure_ascii=False),
        "status": "ready",
        "priority": 20,
        "scheduled_at": _now() - 300,
        "expires_at": _now() + 86400,
        "delivered_at": None,
        "created_at": _now() - 7200,
    },
}


def _overview() -> dict[str, Any]:
    return {
        "ok": True,
        "data": {
            "enabled": True,
            "mode": "companion_center",
            "focus": 0.72,
            "pressure": 0.18,
            "risk_level": "low",
            "concept_nodes": 12,
            "concept_edges": 18,
            "gallery": {
                "enabled": True,
                "configured": True,
                "contract_version": "plana.gallery.candidates.v1",
                "local_loopback_only": True,
                "last_error": "",
            },
            "tables": {
                "episodic_memories": 28,
                "semantic_memories": 9,
                "tool_memories": 2,
                "workflow_runs": len(RUNS),
                "task_records": 3,
            },
            "features": {
                "memory_activation": True,
                "memory_consolidation": True,
                "memory_decay": False,
                "relation_graph": True,
                "concept_extraction": True,
                "structured_memory_extraction": True,
                "memory_query_planner": True,
                "recall_tool": True,
                "recall_engine": "hybrid",
                "memory_kinds": ["episodic", "semantic", "tool", "profile"],
                "task_queue": True,
                "domain_governance": {
                    "enabled": True,
                    "mode": "core_governed",
                    "security_doctor": {
                        "status": "warn",
                        "summary": {"high": 0, "warn": 1, "info": 2},
                        "checks": [
                            {
                                "id": "domain_plugin_boundary",
                                "severity": "info",
                                "status": "ok",
                                "summary": "领域插件保持提案与执行分离。",
                                "recommendation": "继续由 Core 负责授权与执行边界。",
                            },
                            {
                                "id": "write_confirmation",
                                "severity": "warn",
                                "status": "review",
                                "summary": "预览运行包含写入步骤。",
                                "recommendation": "需要显式审批后再执行。",
                            },
                        ],
                    },
                },
            },
        },
    }

