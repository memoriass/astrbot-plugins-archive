from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..skills.integrity import file_hash
from ..skills.models import CONTRACT_VERSION, SkillDraft
from ..skills.scanner import SCANNER_VERSION

DoctorSeverity = Literal["ok", "info", "warn", "high"]

_SCORES: dict[DoctorSeverity, int] = {
    "ok": 0,
    "info": 1,
    "warn": 2,
    "high": 3,
}


@dataclass(slots=True)
class DoctorFinding:
    id: str
    severity: DoctorSeverity
    status: str
    summary: str
    detail: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "severity": self.severity,
            "status": self.status,
            "summary": self.summary,
            "detail": self.detail,
            "recommendation": self.recommendation,
        }


class SkillCenterDoctor:
    """Read-only governance diagnostics for quarantined and exported skills."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def report(
        self,
        *,
        loopback_only: bool | None = None,
        register_llm_tool: bool | None = None,
    ) -> dict[str, Any]:
        checks: list[DoctorFinding] = []
        drafts = self.manager.store.list(status="", limit=200)
        self._check_contract(checks)
        self._check_loopback(checks, loopback_only)
        self._check_llm_tool(checks, register_llm_tool)
        self._check_policy(checks)
        self._check_limits(checks)
        self._check_scanner_versions(checks, drafts)
        self._check_export_integrity(checks, drafts)
        return {
            "status": self._overall_status(checks),
            "summary": self._summary(checks),
            "checks": [item.to_dict() for item in checks],
            "counts": self._counts(drafts),
            "hermes_alignment": {
                "quarantine": True,
                "static_scan": True,
                "approval_required": True,
                "integrity_hashes": True,
                "auto_install": False,
                "executes_side_effects": False,
            },
        }

    def _check_contract(self, checks: list[DoctorFinding]) -> None:
        checks.append(
            DoctorFinding(
                "skill.contract",
                "ok",
                "pass",
                "Skill governance contract is fixed.",
                detail=CONTRACT_VERSION,
            )
        )

    def _check_loopback(
        self,
        checks: list[DoctorFinding],
        loopback_only: bool | None,
    ) -> None:
        if loopback_only is None:
            return
        if loopback_only:
            checks.append(
                DoctorFinding(
                    "skill.loopback_only",
                    "ok",
                    "pass",
                    "HTTP APIs are limited to local loopback calls.",
                )
            )
            return
        checks.append(
            DoctorFinding(
                "skill.loopback_only",
                "high",
                "fail",
                "HTTP APIs are not loopback-only.",
                recommendation="Keep Skill Center behind AstrBot loopback and route external access through Bridge if needed.",
            )
        )

    def _check_llm_tool(
        self,
        checks: list[DoctorFinding],
        register_llm_tool: bool | None,
    ) -> None:
        if register_llm_tool is None:
            return
        checks.append(
            DoctorFinding(
                "skill.llm_tool",
                "warn" if register_llm_tool else "ok",
                "registered" if register_llm_tool else "disabled",
                "LLM skill proposal tool writes to quarantine only."
                if register_llm_tool
                else "LLM skill proposal tool is disabled by default.",
                recommendation="Keep disabled unless the operator wants model-generated drafts in quarantine."
                if register_llm_tool
                else "",
            )
        )

    def _check_policy(self, checks: list[DoctorFinding]) -> None:
        if self.manager.allow_dangerous_approval:
            checks.append(
                DoctorFinding(
                    "skill.dangerous_approval",
                    "high",
                    "review",
                    "Dangerous scan results can be approved.",
                    recommendation="Keep allow_dangerous_approval=false outside a controlled review session.",
                )
            )
            return
        checks.append(
            DoctorFinding(
                "skill.dangerous_approval",
                "ok",
                "pass",
                "Dangerous scan results are blocked from approval.",
            )
        )

    def _check_limits(self, checks: list[DoctorFinding]) -> None:
        if self.manager.max_body_chars > 100_000:
            checks.append(
                DoctorFinding(
                    "skill.body_limit",
                    "warn",
                    "review",
                    "Skill body size limit is unusually high.",
                    detail=f"max_body_chars={self.manager.max_body_chars}",
                    recommendation="Keep generated skill bodies small enough for human review.",
                )
            )
            return
        checks.append(
            DoctorFinding(
                "skill.body_limit",
                "ok",
                "pass",
                "Skill body size limit is reviewable.",
                detail=f"max_body_chars={self.manager.max_body_chars}",
            )
        )

    def _check_scanner_versions(
        self,
        checks: list[DoctorFinding],
        drafts: list[SkillDraft],
    ) -> None:
        stale = [
            draft.id
            for draft in drafts
            if draft.scanner_version and draft.scanner_version != SCANNER_VERSION
        ]
        if stale:
            checks.append(
                DoctorFinding(
                    "skill.scanner_version",
                    "info",
                    "stale",
                    "Some drafts were scanned by an older scanner version.",
                    detail=", ".join(str(item) for item in stale[:20]),
                    recommendation="Re-propose or rescan before approving old drafts.",
                )
            )
            return
        checks.append(
            DoctorFinding(
                "skill.scanner_version",
                "ok",
                "pass",
                "Visible drafts match the current scanner version.",
            )
        )

    def _check_export_integrity(
        self,
        checks: list[DoctorFinding],
        drafts: list[SkillDraft],
    ) -> None:
        drifted: list[str] = []
        missing: list[str] = []
        for draft in drafts:
            if draft.status != "exported" or not draft.exported_path:
                continue
            path = Path(draft.exported_path)
            if not path.is_file():
                missing.append(str(draft.id))
                continue
            try:
                actual = file_hash(path)
            except OSError:
                missing.append(str(draft.id))
                continue
            if draft.exported_hash and actual != draft.exported_hash:
                drifted.append(str(draft.id))
        if drifted or missing:
            checks.append(
                DoctorFinding(
                    "skill.export_integrity",
                    "high",
                    "fail",
                    "Some exported skills are missing or hash-drifted.",
                    detail=f"missing={','.join(missing[:20])}; drifted={','.join(drifted[:20])}",
                    recommendation="Re-export approved drafts before Core reads recipe hints.",
                )
            )
            return
        checks.append(
            DoctorFinding(
                "skill.export_integrity",
                "ok",
                "pass",
                "Exported SKILL.md files match recorded hashes.",
            )
        )

    def _overall_status(self, checks: list[DoctorFinding]) -> str:
        score = max((_SCORES[item.severity] for item in checks), default=0)
        if score >= _SCORES["high"]:
            return "red"
        if score >= _SCORES["warn"]:
            return "yellow"
        return "green"

    def _summary(self, checks: list[DoctorFinding]) -> dict[str, int]:
        return {
            "high": sum(1 for item in checks if item.severity == "high"),
            "warn": sum(1 for item in checks if item.severity == "warn"),
            "info": sum(1 for item in checks if item.severity == "info"),
            "ok": sum(1 for item in checks if item.severity == "ok"),
        }

    def _counts(self, drafts: list[SkillDraft]) -> dict[str, int]:
        counts = {"quarantined": 0, "approved": 0, "rejected": 0, "exported": 0}
        for draft in drafts:
            if draft.status in counts:
                counts[draft.status] += 1
        return counts
