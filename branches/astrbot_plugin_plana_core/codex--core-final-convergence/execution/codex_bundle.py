from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


CODEX_EXECUTION_BUNDLE_VERSION = "plana.codex.execution.v1"


def stable_bundle_hash(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CodexExecutionBundle:
    mode: str
    objective: str
    workflow_run_id: int | None = None
    workflow_hash: str = ""
    step_id: str = ""
    step_capability: str = ""
    step_input: dict[str, Any] = field(default_factory=dict)
    skill_snapshots: tuple[dict[str, Any], ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    write_scope: str = "workspace_only"
    confirmation_grant: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    expected_artifacts: tuple[str, ...] = ()
    verification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return normalize_codex_execution_bundle({
            "contract_version": CODEX_EXECUTION_BUNDLE_VERSION,
            "mode": self.mode,
            "objective": self.objective,
            "workflow_run_id": self.workflow_run_id,
            "workflow_hash": self.workflow_hash,
            "step_id": self.step_id,
            "step_capability": self.step_capability,
            "step_input": dict(self.step_input),
            "skill_snapshots": [dict(item) for item in self.skill_snapshots],
            "allowed_capabilities": list(self.allowed_capabilities),
            "write_scope": self.write_scope,
            "confirmation_grant": dict(self.confirmation_grant),
            "checkpoint": dict(self.checkpoint),
            "expected_artifacts": list(self.expected_artifacts),
            "verification": dict(self.verification),
        })


def normalize_codex_execution_bundle(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("codex_execution_bundle_must_be_mapping")
    normalized = dict(payload)
    if normalized.get("contract_version") != CODEX_EXECUTION_BUNDLE_VERSION:
        raise ValueError("codex_execution_bundle_version_unsupported")
    if normalized.get("mode") not in {"freeform_task", "workflow_step"}:
        raise ValueError("codex_execution_bundle_mode_invalid")
    if not str(normalized.get("objective") or "").strip():
        raise ValueError("codex_execution_bundle_objective_required")
    if str(normalized.get("write_scope") or "workspace_only") not in {
        "workspace_only",
        "system_confirmed",
    }:
        raise ValueError("codex_execution_bundle_write_scope_invalid")
    grant = normalized.get("confirmation_grant")
    if not isinstance(grant, dict):
        raise ValueError("codex_execution_bundle_confirmation_grant_invalid")
    if normalized.get("write_scope") == "system_confirmed" and grant.get("confirmed") is not True:
        raise ValueError("codex_execution_bundle_system_write_not_confirmed")
    supplied_hash = str(normalized.pop("bundle_hash", "") or "")
    actual_hash = stable_bundle_hash(normalized)
    if supplied_hash and supplied_hash != actual_hash:
        raise ValueError("codex_execution_bundle_hash_mismatch")
    normalized["bundle_hash"] = actual_hash
    return normalized
