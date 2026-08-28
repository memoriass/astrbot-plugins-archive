from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

catalog_spec = importlib.util.spec_from_file_location(
    "plana_preview_integration_catalog",
    ROOT / "web" / "integration_catalog.py",
)
assert catalog_spec is not None and catalog_spec.loader is not None
catalog_module = importlib.util.module_from_spec(catalog_spec)
catalog_spec.loader.exec_module(catalog_module)
adapter_metadata = catalog_module.adapter_metadata
capability_metadata = catalog_module.capability_metadata
from preview_web_fixtures import (
    FEEDBACK_QUEUE,
    PROACTIVE,
    RECALL_GAPS,
    RUNS,
    _now,
    _overview,
    _workflow_run,
)
from preview_web_runtime_fixtures import domains_payload, memory_scopes_payload, proactive_payload, remote_tasks_payload, tasks_payload


def json_response(path: str, query: dict[str, list[str]], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    if path == "/api/auth-info":
        return 200, {
            "auth_required": False,
            "auth_model": "astrbot_dashboard_or_loopback",
            "loopback_access": True,
            "astrbot_dashboard_user": False,
        }
    if path == "/api/overview":
        return 200, _overview()
    if path == "/api/resources":
        now = _now()
        resources = [
            {"resource_id": "device:plana-core", "service_ref": "plana.core", "resource_type": "server", "display_name": "Plana Core · 201", "status": "active", "source": "runtime", "updated_at": now, "description": "Core 治理、确认、审计与工作流执行入口。", "metadata": {}},
            {"resource_id": "service:plana-bridge", "service_ref": "plana.bridge", "resource_type": "service", "display_name": "Bridge Gateway · 201", "status": "active", "source": "runtime", "updated_at": now, "description": "连接 Core、Codex Runner 与内部适配服务。", "metadata": {}},
            {"resource_id": "device:codex-runner", "service_ref": "codex.runner", "resource_type": "remote", "display_name": "Codex Runner · 202", "status": "active", "source": "runtime", "updated_at": now, "description": "隔离执行长任务、工具任务和受控 workflow 步骤。", "metadata": {}},
            {"resource_id": "service:adapter-gateway", "service_ref": "adapter.gateway", "resource_type": "service", "display_name": "Adapter Gateway · 202", "status": "active", "source": "runtime", "updated_at": now, "description": "向 Codex Runner 提供受控模型适配。", "metadata": {}},
            {"resource_id": "service:memory-warehouse", "service_ref": "plana.memory_warehouse", "resource_type": "service", "display_name": "Memory Warehouse · 201", "status": "active", "source": "runtime", "updated_at": now, "description": "独立保存长期 evidence、索引和保留状态。", "metadata": {}},
        ]
        return 200, {"ok": True, "data": {"resources": resources, "services": [], "operational": {"status": "degraded", "generated_at": now}, "counts": {"display_resources": len(resources)}}}
    if path == "/api/integrations":
        return 200, {"ok": True, "data": _preview_integrations()}
    if path == "/api/diagnostics":
        now = _now()
        return 200, {
            "ok": True,
            "data": {
                "generated_at": now,
                "overall": {"status": "attention", "issue_count": 0, "warning_count": 1, "service_count": 2},
                "runtime": {"build": {"build_id": "preview"}, "enabled": True, "mode": "normal", "jobs": {"running": 0}, "task_queue": True},
                "services": [
                    {"resource_id": "device:plana-core", "service_ref": "plana.core", "name": "Plana Core · 201", "status": "active", "tone": "success", "description": "Core 治理与执行入口。", "error": "", "updated_at": now},
                    {"resource_id": "device:codex-runner", "service_ref": "codex.runner", "name": "Codex Runner · 202", "status": "active", "tone": "success", "description": "隔离执行与自验证。", "error": "", "updated_at": now},
                    {"resource_id": "service:memory-warehouse", "service_ref": "plana.memory_warehouse", "name": "Memory Warehouse · 201", "status": "active", "tone": "success", "description": "独立 evidence 仓库与索引可用。", "error": "", "updated_at": now},
                ],
                "governance": {"registered_capabilities": 12, "allowed_capabilities": 10, "candidate_counts": {"quarantined": 1}, "remote_tasks": {"active": 0, "completed": 4, "failed": 0, "stale": 0}},
                "data_health": {"validation": {"status": "green", "checks": []}, "tables": {"workflow_runs": len(RUNS)}, "backups": 0, "last_maintenance": {}},
                "findings": [],
                "recent_audit": [],
                "technical": {"preview": True},
            },
        }
    if path == "/api/memories":
        return 200, {
            "ok": True,
            "data": [
                {
                    "id": 1,
                    "kind": "episodic",
                    "content": "Core 接收用户意图，并把有风险的写入路由到待审批队列。",
                    "importance": 0.82,
                    "source": "preview",
                    "created_at": _now() - 7200,
                    "atoms": [
                        {
                            "id": 11,
                            "type": "fact",
                            "content": "有风险的写入必须进入待审批队列。",
                            "status": "active",
                            "ttl_days": 180,
                            "temporal_score": 0.81,
                            "final_score": 0.88,
                        }
                    ],
                },
                {
                    "id": 2,
                    "kind": "semantic",
                    "content": "领域插件负责业务提案，Core 负责复核、授权与执行边界。",
                    "importance": 0.91,
                    "source": "preview",
                    "created_at": _now() - 3600,
                    "atoms": [
                        {
                            "id": 21,
                            "type": "preference",
                            "content": "用户倾向由 Core 统一复核工作流风险。",
                            "status": "active",
                            "ttl_days": 365,
                            "temporal_score": 0.93,
                            "final_score": 0.95,
                        }
                    ],
                },
            ],
        }
    if path == "/api/retrieve-test":
        return 200, {
            "ok": True,
            "data": {
                "fused_results": [
                    {
                        "id": "preview-1",
                        "route": "memory",
                        "title": "领域操作治理",
                        "content": "有副作用的领域操作需要经过 Core 策略复核。",
                        "score": 0.88,
                    }
                ],
                "memories": [1, 2],
                "semantics": [1],
                "concepts": ["companion_core", "domain_governance"],
            },
        }
    if path == "/api/context-preview":
        return 200, {
            "ok": True,
            "data": {
                "preview_lines": [
                    "[Core] 意图路由在本地规则边界内完成",
                    "[Domain] 领域插件只提交结构化操作提案",
                    "[Policy] Core 冻结授权范围并签发短期执行租约",
                ]
            },
        }
    if path == "/api/profile":
        return 200, {
            "ok": True,
            "data": {
                "summary": {
                    "semantic_items": 4,
                    "relationship_edges": 3,
                    "preferences": 1,
                    "promises": 0,
                },
                "semantics": [],
                "relations": [],
            },
        }
    if path == "/api/bridge-status":
        return 200, {
            "ok": True,
            "data": {
                "plugin": "plana_bridge_gateway",
                "status": {
                    "bridge_plugin": "astrbot_plugin_plana_bridge_gateway",
                    "direct_runtime_dependency": False,
                    "enabled": True,
                    "bridge_required": True,
                },
                "supported_kinds": ["memory_query", "execution_observation", "context_sync"],
            },
        }
    if path == "/api/concepts":
        concept_nodes = [
            {"id": 1, "concept": "companion_core", "weight": 4.2, "memory_items": "陪伴中枢负责复核、确认和结果交付", "last_modified": _now()},
            {"id": 2, "concept": "domain_governance", "weight": 3.6, "memory_items": "领域插件提供语义和结构化操作提案", "last_modified": _now()},
            {"id": 3, "concept": "execution_lease", "weight": 2.8, "memory_items": "写操作仅在有效执行租约内运行", "last_modified": _now()},
            {"id": 4, "concept": "risk_review", "weight": 2.4, "memory_items": "写入步骤需要显式确认", "last_modified": _now()},
            {"id": 5, "concept": "user_profile", "weight": 2.0, "memory_items": "用户理解用于内部参考", "last_modified": _now()},
            {"id": 6, "concept": "memory_feedback", "weight": 1.8, "memory_items": "反馈进入待处理队列", "last_modified": _now()},
            {"id": 7, "concept": "episode_summary", "weight": 1.4, "memory_items": "episode 作为证据链摘要", "last_modified": _now()},
        ]
        for i in range(8, 58):
            cluster = ["domain", "lease", "risk", "profile", "memory"][i % 5]
            concept_nodes.append(
                {
                    "id": i,
                    "concept": f"{cluster}_concept_{i:02d}",
                    "weight": round(1.0 + (i % 9) * 0.23, 2),
                    "memory_items": f"{cluster} 模拟记忆节点 {i}",
                    "last_modified": _now() - i * 60,
                }
            )
        concept_edges = [
            {"source": "companion_core", "target": "domain_governance", "strength": 5, "last_modified": _now()},
            {"source": "companion_core", "target": "risk_review", "strength": 4, "last_modified": _now()},
            {"source": "domain_governance", "target": "execution_lease", "strength": 3, "last_modified": _now()},
            {"source": "risk_review", "target": "memory_feedback", "strength": 3, "last_modified": _now()},
            {"source": "user_profile", "target": "memory_feedback", "strength": 2, "last_modified": _now()},
            {"source": "episode_summary", "target": "user_profile", "strength": 2, "last_modified": _now()},
            {"source": "episode_summary", "target": "companion_core", "strength": 1, "last_modified": _now()},
        ]
        hubs = ["companion_core", "domain_governance", "execution_lease", "risk_review", "user_profile"]
        for i, node in enumerate(concept_nodes[7:], start=8):
            concept_edges.append(
                {
                    "source": hubs[i % len(hubs)],
                    "target": node["concept"],
                    "strength": 1 + i % 4,
                    "last_modified": _now() - i * 30,
                }
            )
            if i > 9:
                concept_edges.append(
                    {
                        "source": concept_nodes[i - 3]["concept"],
                        "target": node["concept"],
                        "strength": 1 + i % 3,
                        "last_modified": _now() - i * 30,
                    }
                )
        return 200, {
            "ok": True,
            "data": {
                "nodes": concept_nodes,
                "edges": concept_edges,
                "total_nodes": len(concept_nodes),
                "total_edges": len(concept_edges),
            },
        }
    if path == "/api/relations":
        return 200, {"ok": True, "data": []}
    if path == "/api/memory-scopes":
        pending_feedback = len([item for item in FEEDBACK_QUEUE if item["status"] == "pending"])
        open_gaps = len([item for item in RECALL_GAPS if item["status"] == "open"])
        return 200, {"ok": True, "data": memory_scopes_payload(pending_feedback=pending_feedback, open_gaps=open_gaps)}
    if path == "/api/domains":
        return 200, {"ok": True, "data": domains_payload()}
    if path == "/api/remote-tasks":
        return 200, {"ok": True, "data": remote_tasks_payload(_now())}
    if path == "/api/remote-tasks/cancel":
        return 200, {"ok": True, "result": {"status": "cancelled", "preview": True}}
    if path == "/api/tasks":
        return 200, {"ok": True, "data": tasks_payload(_now())}
    if path == "/api/proactive":
        return 200, {"ok": True, **proactive_payload(PROACTIVE)}
    if path == "/api/workflows":
        return 200, {"ok": True, "runs": list(RUNS.values()), "count": len(RUNS)}
    if path == "/api/recall-gaps":
        status = (query.get("status") or ["open"])[0]
        items = [g for g in RECALL_GAPS if g["status"] == status]
        stats = {name: len([g for g in RECALL_GAPS if g["status"] == name]) for name in ("open", "candidate", "resolved")}
        return 200, {"ok": True, "scope": "global", "status": status, "items": items, "stats": stats}
    if path == "/api/recall-gaps/propose":
        gap_id = int(body.get("gap_id") or 0)
        gap = next((g for g in RECALL_GAPS if int(g["id"]) == gap_id), None)
        content = str(body.get("content") or "").strip()
        if not gap or gap["status"] != "open" or not content:
            return 400, {"ok": False, "result": {"queued": False, "error": "invalid_gap"}}
        feedback_id = max([int(f["id"]) for f in FEEDBACK_QUEUE] or [0]) + 1
        FEEDBACK_QUEUE.append(
            {
                "id": feedback_id,
                "scope_id": "global",
                "user_id": "preview-user",
                "kind": "new_memory",
                "payload": {"content": content, "kind": body.get("kind") or "semantic_note"},
                "status": "pending",
                "created_at": _now(),
            }
        )
        gap["status"] = "candidate"
        gap["candidate_feedback_id"] = feedback_id
        gap["candidate_at"] = _now()
        return 200, {"ok": True, "result": {"queued": True, "feedback_id": feedback_id, "gap_id": gap_id, "gap": gap}}
    if path == "/api/feedback":
        pending = [f for f in FEEDBACK_QUEUE if f["status"] == "pending"]
        return 200, {
            "ok": True,
            "items": pending,
            "stats": {
                "pending": len(pending),
                "new_memory_pending": len([f for f in pending if f["kind"] == "new_memory"]),
                "processed": len([f for f in FEEDBACK_QUEUE if f["status"] == "processed"]),
            },
        }
    if path == "/api/feedback/process":
        processed_ids = []
        for item in FEEDBACK_QUEUE:
            if item["status"] == "pending":
                item["status"] = "processed"
                processed_ids.append(item["id"])
        resolved = []
        for gap in RECALL_GAPS:
            if gap["status"] == "candidate" and gap.get("candidate_feedback_id") in processed_ids:
                gap["status"] = "resolved"
                gap["resolved_at"] = _now()
                gap["resolved_by"] = "feedback_processed"
                resolved.append(gap["id"])
        return 200, {"ok": True, "scope": "global", "stats": {"processed": len(processed_ids), "created": len(processed_ids)}, "recall_gap_resolved": resolved}
    if path in {"/api/scope/aliases", "/api/scope-aliases"}:
        return 200, {
            "ok": True,
            "aliases": [
                {"alias": "main_chat", "canonical": "global", "created_at": _now() - 3600},
                {"alias": "workflow_lab", "canonical": "global", "created_at": _now() - 1800},
            ],
        }
    if path == "/api/workflows/get":
        run_id = int((query.get("id") or ["1001"])[0])
        run = RUNS.get(run_id)
        return (200, {"ok": True, "run": run}) if run else (404, {"ok": False, "error": "not_found"})
    if path == "/api/workflows/review":
        run_id = int((query.get("id") or ["1001"])[0])
        run = RUNS.get(run_id)
        if not run:
            return 404, {"ok": False, "review": {"ok": False, "error": "not_found"}}
        return 200, {
            "ok": True,
            "review": {
                "ok": True,
                "status": "ready",
                "would_execute": False,
                "drift_errors": [],
                "compile_errors": [],
                "current_hashes": {
                    "proposal_hash": run["proposal_hash"],
                    "capability_view_hash": run["capability_view_hash"],
                },
            },
        }
    if path == "/api/workflows/run":
        run_id = max(RUNS) + 1
        goal = str(body.get("intent") or "预览工作流请求")
        RUNS[run_id] = _workflow_run(run_id, goal)
        return 200, {"ok": True, "result": RUNS[run_id]["result"]}
    if path in {"/api/workflows/confirm", "/api/workflows/cancel"}:
        run_id = int(body.get("id") or 0)
        if run_id in RUNS:
            RUNS[run_id]["status"] = "completed" if path.endswith("confirm") else "cancelled"
        return 200, {"ok": True, "result": RUNS.get(run_id, {})}
    if path == "/api/skills":
        return 200, {
            "ok": True,
            "data": {
                "skill_center": {
                    "configured": True,
                    "required": False,
                    "contract_version": "preview-v1",
                    "last_error": "",
                },
                "degraded": False,
                "candidates": [
                    {
                        "skill_center_id": "skill-preview-001",
                        "skill_name": "workflow_review_helper",
                        "source": "skill_center_export",
                        "governance_status": "approved",
                        "scan_verdict": "pass",
                        "description": "用于工作流复核的只读辅助工作配方。",
                        "risk_notes": ["read_only"],
                        "skill_path": "skills/workflow_review_helper",
                    }
                ],
            },
        }
    if path == "/api/skill-center/status":
        return 200, {"ok": True, "data": {"ok": True, "configured": True}}
    if path == "/api/maintenance-status":
        return 200, {
            "ok": True,
            "data": {
                "db_path": "preview-only",
                "tables": {"workflow_runs": len(RUNS)},
                "validation": {
                    "status": "preview",
                    "checks": [{"name": "preview_api", "status": "ok", "detail": "stubbed"}],
                },
                "backups": [],
            },
        }
    if path in {"/api/backup", "/api/rebuild-indexes", "/api/maintain"}:
        return 200, {"ok": True, "data": {"preview": True, "action": path.rsplit("/", 1)[-1]}}
    return 404, {"ok": False, "error": "not_found", "path": path}


def _preview_integrations() -> dict[str, Any]:
    now = _now()
    service_prefixes = {
        "ani_rss.production": "ani_rss.",
        "ncqq.production": "ncqq.",
        "qbittorrent.production": "qbittorrent.",
        "qbittorrent.tianxue": "tianxue_qb.",
        "komga.production": "komga.",
    }
    write_capabilities = {
        "ncqq.control_instance", "ncqq.create_instance", "ncqq.refresh_login",
        "ncqq.inject_backend", "ncqq.delete_instance_keep_data",
        "ani_rss.add_subscription_from_rss",
        "ani_rss.set_subscription_enabled", "ani_rss.refresh_subscription",
        "ani_rss.refresh_all", "ani_rss.delete_subscription",
        "qbittorrent.add_torrent_url", "qbittorrent.control_torrent",
        "qbittorrent.set_category", "qbittorrent.delete_torrent_keep_files",
        "komga.scan_library", "komga.analyze_library",
        "komga.refresh_library_metadata", "komga.refresh_series_metadata",
    }
    adapters = []
    for service_ref, metadata in catalog_module.ADAPTER_CATALOG.items():
        prefix = service_prefixes.get(service_ref, "")
        capability_names = sorted(name for name in catalog_module.CAPABILITY_CATALOG if prefix and name.startswith(prefix))
        metadata = adapter_metadata(service_ref)
        probe = str(metadata.get("health_capability") or "")
        management = str(metadata.get("management") or "controlled")
        protected = management == "protected"
        read_only_external = management == "read_only_external"
        capabilities = []
        for capability_name in capability_names:
            capability = capability_metadata(capability_name)
            read_only = capability_name not in write_capabilities
            capability.update(
                {
                    "capability": capability_name,
                    "availability": "available",
                    "read_only": read_only,
                    "confirmation": "not_required" if read_only else "core_required",
                    "lanes": ["interactive"],
                    "default_arguments": {},
                    "registered_on_gateway": True,
                    "probe_capability": probe,
                    "derived": capability_name != probe,
                    "checked_at": now,
                    "error": "",
                    "limitations": [],
                }
            )
            capabilities.append(capability)
        adapters.append(
            {
                "service_ref": service_ref,
                "name": metadata["name"],
                "copy_key": metadata["copy_key"],
                "target": metadata["target"],
                "deployment": metadata["deployment"],
                "protocol": metadata["protocol"],
                "authentication": metadata["authentication"],
                "authentication_key": metadata["authentication_key"],
                "trust_boundary": metadata["trust_boundary"],
                "trust_boundary_key": metadata["trust_boundary_key"],
                "credential_managed": bool(metadata.get("credential_ref")),
                "health_capability": probe,
                "status": "protected" if protected else "available",
                "credential_status": "not_applicable" if protected else "not_required" if read_only_external else "configured",
                "owner": metadata.get("owner", "core"),
                "management": management,
                "child_resources": [
                    {
                        "service_ref": "qbittorrent.ani",
                        "parent_service_ref": "ani_rss.production",
                        "kind": "qbittorrent",
                        "owner": "ani_rss",
                        "management": "read_only_external",
                        "endpoint_role": "ani_rss_download",
                    }
                ] if service_ref == "ani_rss.production" else [],
                "capability_count": len(capabilities),
                "available_count": len(capabilities),
                "read_only_count": sum(item["read_only"] for item in capabilities),
                "artifact_count": sum(bool(item.get("artifact")) for item in capabilities),
                "capabilities": capabilities,
            }
        )
    total = sum(item["capability_count"] for item in adapters)
    return {
        "gateway": {
            "service_ref": "adapter.gateway",
            "name": "Adapter Gateway",
            "host": "202",
            "status": "active",
            "configured": True,
            "executes_tasks": False,
            "adapter_count": len(adapters),
            "capability_count": total,
            "available_count": total,
        },
        "summary": {
            "adapters": len(adapters),
            "capabilities": total,
            "available": total,
            "read_only": sum(item["read_only_count"] for item in adapters),
            "artifacts": 1,
            "restricted": 0,
            "issues": 0,
        },
        "adapters": adapters,
        "technical": {"preview": True},
    }

