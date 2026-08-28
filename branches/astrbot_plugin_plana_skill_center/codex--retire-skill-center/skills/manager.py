from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..diagnostics import SkillCenterDoctor
from .integrity import export_manifest, file_hash, skill_body_hash, write_manifest
from .models import CONTRACT_VERSION, SkillDraft
from .scanner import RULESET_HASH, SCANNER_VERSION, SkillScanner
from .store import SkillDraftStore


_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class SkillCenterManager:
    """Govern generated skills before they can leave quarantine."""

    def __init__(
        self,
        data_dir: Path | str,
        *,
        max_body_chars: int = 30000,
        allow_dangerous_approval: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.max_body_chars = max(1000, min(int(max_body_chars or 30000), 200000))
        self.allow_dangerous_approval = bool(allow_dangerous_approval)
        self.store = SkillDraftStore(self.data_dir / "skill_center.sqlite3")
        self.scanner = SkillScanner()
        self.export_root = self.data_dir / "approved"
        self.doctor = SkillCenterDoctor(self)

    def initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.store.initialize()

    def status(
        self,
        *,
        loopback_only: bool | None = None,
        register_llm_tool: bool | None = None,
    ) -> dict[str, Any]:
        drafts = self.store.list(limit=200)
        stale_ruleset = [
            draft.id
            for draft in drafts
            if str(draft.scan.get("ruleset_hash") or "") != RULESET_HASH
        ]
        return {
            "ok": True,
            "center": "plana_skill_center",
            "contract_version": CONTRACT_VERSION,
            "governance": {
                "quarantine": True,
                "static_scan": True,
                "approval_required": True,
                "integrity_hashes": True,
                "export_drift_guard": True,
                "executes_side_effects": False,
                "auto_install": False,
                "allow_dangerous_approval": self.allow_dangerous_approval,
                "scanner_ruleset_hash": RULESET_HASH,
                "rescan_required": bool(stale_ruleset),
                "rescan_required_count": len(stale_ruleset),
            },
            "limits": {"max_skill_body_chars": self.max_body_chars},
            "security_doctor": self.doctor.report(
                loopback_only=loopback_only,
                register_llm_tool=register_llm_tool,
            ),
        }

    def propose_skill(
        self,
        *,
        name: str = "",
        description: str = "",
        body: str = "",
        source: str = "agent-created",
        trust_level: str = "agent-created",
        source_uri: str = "",
        origin_model: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalize_body(
            name=name,
            description=description,
            body=body,
        )
        if not normalized["ok"]:
            return normalized

        final_name = normalized["name"]
        final_body = normalized["body"]
        body_hash = skill_body_hash(final_body)
        scan = self.scanner.scan(final_body, trust_level=trust_level).to_dict()
        draft = self.store.create(
            slug=self._slugify(final_name),
            name=final_name,
            description=str(description or "").strip()[:500],
            source=str(source or "agent-created").strip()[:200],
            trust_level=str(scan.get("trust_level") or "agent-created"),
            body=final_body,
            scan=scan,
            body_hash=body_hash,
            source_uri=str(source_uri or "").strip()[:500],
            origin_model=str(origin_model or "").strip()[:120],
            scanner_version=str(scan.get("scanner_version") or SCANNER_VERSION),
        )
        return {
            "ok": True,
            "draft": draft.to_dict(include_body=False),
            "policy": self._approval_policy(draft),
        }

    def get_skill(self, draft_id: int, *, include_body: bool = False) -> dict[str, Any]:
        draft = self.store.get(int(draft_id), include_body=include_body)
        if draft is None:
            return {"ok": False, "error": "skill_not_found"}
        return {"ok": True, "draft": draft.to_dict(include_body=include_body)}

    def list_skills(self, *, status: str = "", limit: int = 50) -> dict[str, Any]:
        drafts = self.store.list(status=str(status or "").strip(), limit=limit)
        return {
            "ok": True,
            "drafts": [draft.to_dict(include_body=False) for draft in drafts],
        }

    def approve_skill(self, draft_id: int, *, review_actor: str = "") -> dict[str, Any]:
        draft = self.store.get(int(draft_id), include_body=True)
        if draft is None:
            return {"ok": False, "error": "skill_not_found"}
        if draft.status != "quarantined":
            return {
                "ok": False,
                "error": "invalid_status",
                "status": draft.status,
            }

        policy = self._approval_policy(draft)
        if not policy["can_approve"]:
            return {"ok": False, "error": "approval_blocked", "policy": policy}

        current_hash = skill_body_hash(draft.body)
        if draft.body_hash and draft.body_hash != current_hash:
            return {
                "ok": False,
                "error": "approval_drift",
                "field": "body_hash",
                "expected": draft.body_hash,
                "actual": current_hash,
            }

        updated = self.store.update_status(
            draft.id,
            "approved",
            approved_hash=current_hash,
            review_actor=str(review_actor or "local")[:120],
        )
        if updated is None:
            return {"ok": False, "error": "skill_not_found"}
        return {
            "ok": True,
            "draft": updated.to_dict(include_body=False),
            "policy": self._approval_policy(updated),
        }

    def reject_skill(self, draft_id: int) -> dict[str, Any]:
        draft = self.store.get(int(draft_id), include_body=False)
        if draft is None:
            return {"ok": False, "error": "skill_not_found"}
        if draft.status not in {"quarantined", "approved"}:
            return {
                "ok": False,
                "error": "invalid_status",
                "status": draft.status,
            }
        updated = self.store.update_status(draft.id, "rejected")
        if updated is None:
            return {"ok": False, "error": "skill_not_found"}
        return {"ok": True, "draft": updated.to_dict(include_body=False)}

    def export_skill(self, draft_id: int) -> dict[str, Any]:
        draft = self.store.get(int(draft_id), include_body=True)
        if draft is None:
            return {"ok": False, "error": "skill_not_found"}
        if draft.status == "exported" and draft.exported_path:
            return {"ok": True, "draft": draft.to_dict(include_body=False)}
        if draft.status != "approved":
            return {
                "ok": False,
                "error": "not_approved",
                "status": draft.status,
            }

        current_hash = skill_body_hash(draft.body)
        approved_hash = draft.approved_hash or draft.body_hash
        if approved_hash and approved_hash != current_hash:
            return {
                "ok": False,
                "error": "approval_drift",
                "field": "approved_hash",
                "expected": approved_hash,
                "actual": current_hash,
            }

        target_dir = self._export_dir(draft)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"
        target_file.write_text(draft.body, encoding="utf-8", newline="\n")
        exported_hash = file_hash(target_file)
        exported_at = self._unix_now()
        write_manifest(
            target_dir / "plana-skill.json",
            export_manifest(
                contract_version=CONTRACT_VERSION,
                draft_id=draft.id,
                name=draft.name,
                slug=draft.slug,
                source=draft.source,
                source_uri=draft.source_uri,
                trust_level=draft.trust_level,
                body_hash=draft.body_hash or current_hash,
                approved_hash=approved_hash or current_hash,
                exported_hash=exported_hash,
                scanner_version=draft.scanner_version or SCANNER_VERSION,
                ruleset_hash=str(draft.scan.get("ruleset_hash") or RULESET_HASH),
                origin_model=draft.origin_model,
                exported_at=exported_at,
                read_policy=self._export_read_policy(),
                reference_manifest=[],
            ),
        )
        updated = self.store.update_status(
            draft.id,
            "exported",
            exported_path=str(target_file),
            exported_hash=exported_hash,
            exported_at=exported_at,
        )
        if updated is None:
            return {"ok": False, "error": "skill_not_found"}
        return {"ok": True, "draft": updated.to_dict(include_body=False)}

    def _normalize_body(self, *, name: str, description: str, body: str) -> dict[str, Any]:
        raw = str(body or "").replace("\r\n", "\n").strip()
        if not raw:
            return {"ok": False, "error": "empty_skill_body"}
        if len(raw) > self.max_body_chars:
            return {
                "ok": False,
                "error": "skill_body_too_large",
                "limit": self.max_body_chars,
            }

        title = str(name or "").strip()
        match = _TITLE_RE.search(raw)
        if not title and match:
            title = match.group(1).strip()
        title = title[:120] or "Generated Skill"

        if match:
            return {"ok": True, "name": title, "body": raw}

        desc = str(description or "").strip()
        pieces = [f"# {title}", ""]
        if desc:
            pieces.extend([desc, ""])
        pieces.append(raw)
        return {"ok": True, "name": title, "body": "\n".join(pieces).strip() + "\n"}

    def _approval_policy(self, draft: SkillDraft) -> dict[str, Any]:
        verdict = str(draft.scan.get("verdict") or "dangerous")
        findings = draft.scan.get("findings")
        finding_count = len(findings) if isinstance(findings, list) else 0
        can_approve = verdict != "dangerous" or self.allow_dangerous_approval
        reason = "scan_allows_approval"
        if verdict == "dangerous" and not self.allow_dangerous_approval:
            reason = "dangerous_scan_blocked"
        return {
            "can_approve": can_approve,
            "verdict": verdict,
            "finding_count": finding_count,
            "reason": reason,
            "body_hash": draft.body_hash,
            "approved_hash": draft.approved_hash,
            "scanner_version": draft.scanner_version,
        }

    def _export_read_policy(self) -> dict[str, Any]:
        return {
            "runtime": "advisory_recipe_candidate_only",
            "body_mode": "bounded",
            "max_body_chars": min(64_000, self.max_body_chars),
            "references": "manifest_only",
            "executes_side_effects": False,
        }

    def _export_dir(self, draft: SkillDraft) -> Path:
        root = self.export_root.resolve()
        target = (root / f"{draft.id}-{draft.slug}").resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("export_path_escape") from exc
        return target

    def _slugify(self, value: str) -> str:
        slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
        return slug[:80].strip("-") or "skill"

    def _unix_now(self) -> int:
        import time

        return int(time.time())
