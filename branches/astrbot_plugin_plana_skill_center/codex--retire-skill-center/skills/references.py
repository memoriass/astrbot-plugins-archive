from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
import unicodedata


MAX_REFERENCE_FILES = 16
MAX_REFERENCE_BYTES = 256_000


def validate_reference_manifest(
    skill_root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    root = skill_root.resolve()
    if len(entries) > MAX_REFERENCE_FILES:
        return {"ok": False, "error": "reference_file_limit_exceeded"}
    normalized: list[dict[str, Any]] = []
    total_bytes = 0
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return {"ok": False, "error": "reference_entry_invalid"}
        relative = unicodedata.normalize(
            "NFC", str(entry.get("path") or "").replace("\\", "/").strip()
        )
        if not relative or relative.startswith("/") or ":" in relative:
            return {"ok": False, "error": "reference_path_invalid"}
        input_folded = relative.casefold()
        if input_folded in seen:
            return {"ok": False, "error": "reference_path_duplicate"}
        unresolved = root / relative
        if _path_has_link_or_reparse(root, unresolved):
            return {"ok": False, "error": "reference_file_unavailable"}
        candidate = unresolved.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return {"ok": False, "error": "reference_path_escape"}
        if _is_link_or_reparse(candidate) or not candidate.is_file():
            return {"ok": False, "error": "reference_file_unavailable"}
        canonical = unicodedata.normalize("NFC", candidate.relative_to(root).as_posix())
        folded = unicodedata.normalize("NFC", canonical).casefold()
        if folded in seen:
            return {"ok": False, "error": "reference_path_duplicate"}
        seen.add(input_folded)
        seen.add(folded)
        stat = candidate.stat()
        size = stat.st_size
        total_bytes += size
        if total_bytes > MAX_REFERENCE_BYTES:
            return {"ok": False, "error": "reference_byte_limit_exceeded"}
        normalized.append(
            {
                "path": canonical,
                "bytes": size,
                "sha256": _sha256(candidate),
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {
        "ok": True,
        "references": normalized,
        "file_count": len(normalized),
        "total_bytes": total_bytes,
    }


def verify_reference_manifest(
    skill_root: Path,
    approved_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    validation = validate_reference_manifest(skill_root, approved_entries)
    if not validation.get("ok"):
        return validation
    approved = {
        unicodedata.normalize("NFC", str(item.get("path") or "")).casefold(): item
        for item in approved_entries
        if isinstance(item, dict)
    }
    for current in validation["references"]:
        expected = approved.get(current["path"].casefold(), {})
        if str(expected.get("sha256") or "") != current["sha256"]:
            return {
                "ok": False,
                "error": "reference_content_drift",
                "path": current["path"],
            }
        if int(expected.get("bytes") or -1) != current["bytes"]:
            return {
                "ok": False,
                "error": "reference_size_drift",
                "path": current["path"],
            }
    return validation


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if callable(isjunction) and isjunction(path):
        return True
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0) or 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def _path_has_link_or_reparse(root: Path, candidate: Path) -> bool:
    current = root
    try:
        parts = candidate.relative_to(root).parts
    except ValueError:
        return True
    for part in parts:
        current = current / part
        if _is_link_or_reparse(current):
            return True
    return False
