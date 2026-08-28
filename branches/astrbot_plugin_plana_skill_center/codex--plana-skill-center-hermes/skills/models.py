from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CONTRACT_VERSION = "plana.skill.governance.v1"

SkillStatus = Literal["quarantined", "approved", "rejected", "exported"]
TrustLevel = Literal["builtin", "trusted", "community", "agent-created"]
ScanVerdict = Literal["safe", "caution", "dangerous"]


@dataclass(slots=True)
class Finding:
    pattern_id: str
    severity: str
    category: str
    line: int
    match: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "severity": self.severity,
            "category": self.category,
            "line": self.line,
            "match": self.match[:240],
            "description": self.description,
        }


@dataclass(slots=True)
class ScanResult:
    verdict: ScanVerdict
    trust_level: TrustLevel
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    scanner_version: str = ""
    ruleset_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "trust_level": self.trust_level,
            "summary": self.summary,
            "scanner_version": self.scanner_version,
            "ruleset_hash": self.ruleset_hash,
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(slots=True)
class SkillDraft:
    id: int
    slug: str
    name: str
    description: str
    status: SkillStatus
    source: str
    trust_level: TrustLevel
    body_hash: str
    approved_hash: str
    exported_hash: str
    source_uri: str
    origin_model: str
    review_actor: str
    scanner_version: str
    body: str
    scan: dict[str, Any]
    created_at: int
    updated_at: int
    approved_at: int | None = None
    exported_at: int | None = None
    exported_path: str = ""

    def to_dict(self, *, include_body: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "source": self.source,
            "trust_level": self.trust_level,
            "body_hash": self.body_hash,
            "approved_hash": self.approved_hash,
            "exported_hash": self.exported_hash,
            "source_uri": self.source_uri,
            "origin_model": self.origin_model,
            "review_actor": self.review_actor,
            "scanner_version": self.scanner_version,
            "scan": self.scan,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_at": self.approved_at,
            "exported_at": self.exported_at,
            "exported_path": self.exported_path,
        }
        if include_body:
            payload["body"] = self.body
        return payload
