from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def skill_body_hash(body: str) -> str:
    return "sha256:" + hashlib.sha256(str(body or "").encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def export_manifest(
    *,
    contract_version: str,
    draft_id: int,
    name: str,
    slug: str,
    source: str,
    source_uri: str,
    trust_level: str,
    body_hash: str,
    approved_hash: str,
    exported_hash: str,
    scanner_version: str,
    ruleset_hash: str = "",
    origin_model: str = "",
    exported_at: int,
    read_policy: dict[str, Any] | None = None,
    reference_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": contract_version,
        "draft_id": draft_id,
        "name": name,
        "slug": slug,
        "source": source,
        "source_uri": source_uri,
        "trust_level": trust_level,
        "body_hash": body_hash,
        "approved_hash": approved_hash,
        "exported_hash": exported_hash,
        "integrity_status": "verified",
        "scanner_version": scanner_version,
        "ruleset_hash": ruleset_hash,
        "exported_at": exported_at,
        "provenance": {
            "source": source,
            "source_uri": source_uri,
            "origin_model": origin_model,
            "content_digest": body_hash,
            "retrieved_at": exported_at,
        },
        "read_policy": read_policy or {
            "runtime": "advisory_recipe_candidate_only",
            "body_mode": "bounded",
            "max_body_chars": 64000,
            "references": "manifest_only",
            "executes_side_effects": False,
        },
        "reference_manifest": reference_manifest or [],
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
