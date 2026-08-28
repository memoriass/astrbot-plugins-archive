from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_CANDIDATE_OUTPUT_BYTES = 256 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_RE = re.compile(
    r"(?i)(?:(?:api[_-]?key|access[_-]?token|password|cookie|authorization)\s*[:=]\s*)([^\s,;]+)|(?:bearer\s+)([A-Za-z0-9._~+/-]+=*)"
)


class RunnerOutputMixin:
    def _candidate_output_schema(self) -> dict[str, Any]:
        candidate = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "record_id", "kind", "status", "risk_level", "title", "skill_id",
                "skill_version", "content_hash", "error_signature", "evidence_count",
                "expires_at", "content", "verification",
            ],
            "properties": {
                "record_id": {"type": ["string", "null"], "maxLength": 120},
                "kind": {"type": "string", "enum": ["memory", "skill", "failure"]},
                "status": {
                    "type": "string",
                    "enum": ["candidate", "active", "rejected", "quarantined"],
                },
                "risk_level": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
                "title": {"type": "string", "minLength": 1, "maxLength": 180},
                "skill_id": {"type": ["string", "null"], "maxLength": 160},
                "skill_version": {"type": ["string", "null"], "maxLength": 80},
                "content_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                "error_signature": {"type": ["string", "null"], "maxLength": 180},
                "evidence_count": {"type": ["integer", "null"], "minimum": 0, "maximum": 10000},
                "expires_at": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": 2147483647,
                },
                "content": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["pending_id", "action", "auto_approval_reason", "content_hash"],
                    "properties": {
                        "pending_id": {"type": ["string", "null"], "maxLength": 160},
                        "action": {"type": ["string", "null"], "maxLength": 80},
                        "auto_approval_reason": {"type": ["string", "null"], "maxLength": 240},
                        "content_hash": {
                            "type": ["string", "null"],
                            "pattern": "^[0-9a-f]{64}$",
                        },
                    },
                },
                "verification": {"$ref": "#/$defs/verification"},
            },
        }
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "status",
                "result_summary",
                "artifacts",
                "verification",
                "learning_candidates",
                "capability_candidate",
            ],
            "properties": {
                "schema_version": {
                    "type": "string",
                    "const": "plana.codex.candidate-output.v1",
                },
                "status": {"type": "string", "enum": ["succeeded", "partial", "failed"]},
                "result_summary": {"type": "string", "minLength": 1, "maxLength": 6000},
                "artifacts": {
                    "type": "array",
                    "maxItems": 32,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["path", "description"],
                        "properties": {
                            "path": {"type": "string", "minLength": 1, "maxLength": 300},
                            "description": {"type": "string", "maxLength": 500},
                        },
                    },
                },
                "verification": {"$ref": "#/$defs/verification"},
                "learning_candidates": {
                    "type": "array",
                    "maxItems": 32,
                    "items": candidate,
                },
                "capability_candidate": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "required": ["manifest_path", "manifest_json"],
                    "properties": {
                        "manifest_path": {"type": "string", "minLength": 1, "maxLength": 300},
                        "manifest_json": {"type": "string", "minLength": 2, "maxLength": 200000},
                    },
                },
            },
            "$defs": {
                "verification": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["passed", "checks", "risk_reasons"],
                    "properties": {
                        "passed": {"type": "boolean"},
                        "checks": {
                            "type": "array",
                            "maxItems": 32,
                            "items": {"type": "string", "maxLength": 500},
                        },
                        "risk_reasons": {
                            "type": "array",
                            "maxItems": 16,
                            "items": {"type": "string", "maxLength": 300},
                        },
                    },
                }
            },
        }

    def _read_candidate_output(self, path: Path) -> tuple[str, dict[str, Any]]:
        if not path.is_file():
            raise RuntimeError("candidate_output_missing")
        if path.stat().st_size > MAX_CANDIDATE_OUTPUT_BYTES:
            raise RuntimeError("candidate_output_too_large")
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("candidate_output_invalid_json") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("candidate_output_must_be_object")
        required_keys = {
            "schema_version",
            "status",
            "result_summary",
            "artifacts",
            "verification",
            "learning_candidates",
        }
        allowed_keys = {
            *required_keys,
            "capability_candidate",
        }
        if not required_keys.issubset(parsed) or set(parsed) - allowed_keys:
            raise RuntimeError("candidate_output_keys_invalid")
        if parsed.get("schema_version") != "plana.codex.candidate-output.v1":
            raise RuntimeError("candidate_output_schema_version_invalid")
        status = str(parsed.get("status") or "").strip()
        summary = str(parsed.get("result_summary") or "").strip()
        if status not in {"succeeded", "partial", "failed"} or not summary or len(summary) > 6000:
            raise RuntimeError("candidate_output_header_invalid")
        if status == "failed":
            raise RuntimeError("candidate_output_reported_failed")
        artifacts = parsed.get("artifacts")
        verification = parsed.get("verification")
        candidates = parsed.get("learning_candidates")
        capability_candidate = parsed.get("capability_candidate")
        if not isinstance(artifacts, list) or len(artifacts) > 32:
            raise RuntimeError("candidate_output_artifacts_invalid")
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) - {"path", "description"}:
                raise RuntimeError("candidate_output_artifact_invalid")
            workspace = path.parent.parent
            raw_artifact_path = str(artifact.get("path") or "").strip()
            candidate_path = Path(raw_artifact_path)
            if candidate_path.is_absolute():
                try:
                    raw_artifact_path = candidate_path.resolve().relative_to(
                        workspace.resolve()
                    ).as_posix()
                except ValueError as exc:
                    raise RuntimeError("candidate_output_artifact_path_forbidden") from exc
            relative = self._safe_relative_path(raw_artifact_path)
            artifact["path"] = relative.as_posix()
            if relative.parts[0] in {".agents", ".plana"} or relative.as_posix() == "AGENTS.md":
                raise RuntimeError("candidate_output_artifact_path_forbidden")
            if not self._workspace_destination(workspace, relative.as_posix()).is_file():
                raise RuntimeError("candidate_output_artifact_missing")
        self._validate_verification(verification)
        if status == "succeeded" and verification.get("passed") is not True:
            raise RuntimeError("candidate_output_verification_failed")
        if not isinstance(candidates, list) or len(candidates) > 32:
            raise RuntimeError("candidate_output_candidates_invalid")
        for candidate in candidates:
            self._validate_learning_candidate(candidate)
        if capability_candidate is not None:
            if not isinstance(capability_candidate, dict):
                raise RuntimeError("capability_candidate_invalid")
            if set(capability_candidate) != {"manifest_path", "manifest_json"}:
                raise RuntimeError("capability_candidate_keys_invalid")
            workspace = path.parent.parent
            raw_manifest_path = str(capability_candidate.get("manifest_path") or "").strip()
            candidate_path = Path(raw_manifest_path)
            if candidate_path.is_absolute():
                try:
                    raw_manifest_path = candidate_path.resolve().relative_to(
                        workspace.resolve()
                    ).as_posix()
                except ValueError as exc:
                    raise RuntimeError("capability_candidate_manifest_path_forbidden") from exc
            relative = self._safe_relative_path(raw_manifest_path)
            capability_candidate["manifest_path"] = relative.as_posix()
            if not self._workspace_destination(workspace, relative.as_posix()).is_file():
                raise RuntimeError("capability_candidate_manifest_missing")
            try:
                manifest = json.loads(str(capability_candidate.get("manifest_json") or ""))
            except json.JSONDecodeError as exc:
                raise RuntimeError("capability_candidate_manifest_invalid") from exc
            if not isinstance(manifest, dict):
                raise RuntimeError("capability_candidate_manifest_invalid")
            if manifest.get("contract_version") != "plana.capability.candidate.v1":
                raise RuntimeError("capability_candidate_version_invalid")
            if str(manifest.get("status") or "") != "quarantined":
                raise RuntimeError("capability_candidate_status_invalid")
            parsed["capability_candidate"] = manifest
        return self._redact_sensitive(summary), parsed

    def _validate_verification(self, value: object) -> None:
        if not isinstance(value, dict) or set(value) - {"passed", "checks", "risk_reasons"}:
            raise RuntimeError("candidate_verification_invalid")
        if not isinstance(value.get("passed"), bool):
            raise RuntimeError("candidate_verification_passed_invalid")
        for key, maximum in (("checks", 32), ("risk_reasons", 16)):
            entries = value.get(key, [])
            if not isinstance(entries, list) or len(entries) > maximum or not all(
                isinstance(item, str) for item in entries
            ):
                raise RuntimeError(f"candidate_verification_{key}_invalid")

    def _validate_learning_candidate(self, value: object) -> None:
        if not isinstance(value, dict):
            raise RuntimeError("learning_candidate_invalid")
        allowed = {
            "record_id", "kind", "status", "risk_level", "title", "skill_id",
            "skill_version", "content_hash", "error_signature", "evidence_count",
            "expires_at", "content", "verification",
        }
        if set(value) - allowed:
            raise RuntimeError("learning_candidate_keys_invalid")
        if value.get("kind") not in {"memory", "skill", "failure"}:
            raise RuntimeError("learning_candidate_kind_invalid")
        if value.get("status") not in {"candidate", "active", "rejected", "quarantined"}:
            raise RuntimeError("learning_candidate_status_invalid")
        if not str(value.get("title") or "").strip():
            raise RuntimeError("learning_candidate_title_missing")
        content_hash = str(value.get("content_hash") or "").strip().lower()
        if content_hash and not SHA256_RE.fullmatch(content_hash):
            raise RuntimeError("learning_candidate_hash_invalid")
        self._validate_verification(value.get("verification"))

    def _sanitize_structure(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._sanitize_structure(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_structure(item) for item in value]
        if isinstance(value, str):
            return self._redact_sensitive(value)
        return value

    def _redact_sensitive(self, value: str) -> str:
        return SECRET_RE.sub("[REDACTED]", str(value or ""))
