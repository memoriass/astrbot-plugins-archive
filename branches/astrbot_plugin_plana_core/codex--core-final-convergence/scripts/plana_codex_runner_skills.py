from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

CODEX_USER_ID = 1001
CODEX_GROUP_ID = 1001
MAX_TASK_SKILLS = 8
MAX_SKILL_FILES = 32
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_SKILL_TOTAL_BYTES = 384 * 1024
SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_AGENTS_MARKER = "<!-- plana-task-scoped-agents-v1 -->"


class RunnerSkillMixin:
    def _validated_task_skills(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_skills = payload.get("task_skills") or []
        if isinstance(raw_skills, dict):
            raw_skills = [raw_skills]
        if not isinstance(raw_skills, list):
            raise RuntimeError("task_skills_must_be_list")
        if len(raw_skills) > MAX_TASK_SKILLS:
            raise RuntimeError("task_skills_limit_exceeded")
        normalized: list[dict[str, Any]] = []
        names: set[str] = set()
        total_bytes = 0
        for raw_skill in raw_skills:
            if not isinstance(raw_skill, dict):
                raise RuntimeError("task_skill_must_be_object")
            name = str(raw_skill.get("name") or "").strip().lower()
            if not SKILL_NAME_RE.fullmatch(name):
                raise RuntimeError("task_skill_name_invalid")
            if name in names:
                raise RuntimeError("task_skill_name_duplicate")
            names.add(name)
            skill_text = raw_skill.get("skill_md")
            if not isinstance(skill_text, str) or not skill_text.strip():
                raise RuntimeError(f"task_skill_content_missing:{name}")
            skill_bytes = skill_text.encode("utf-8")
            if len(skill_bytes) > MAX_SKILL_FILE_BYTES:
                raise RuntimeError(f"task_skill_file_too_large:{name}:SKILL.md")
            self._verify_content_hash(skill_bytes, raw_skill.get("sha256"), "SKILL.md")
            files = [{"path": "SKILL.md", "content": skill_bytes}]
            seen_paths = {"SKILL.md"}
            for section in ("references", "assets", "files"):
                entries = raw_skill.get(section) or []
                if not isinstance(entries, list):
                    raise RuntimeError(f"task_skill_{section}_must_be_list:{name}")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise RuntimeError(f"task_skill_{section}_entry_invalid:{name}")
                    relative = self._safe_relative_path(
                        entry.get("path"),
                        "" if section == "files" else section,
                    )
                    if relative.as_posix() in seen_paths:
                        raise RuntimeError(f"task_skill_path_duplicate:{name}")
                    seen_paths.add(relative.as_posix())
                    content = self._skill_file_content(
                        entry,
                        binary_allowed=section in {"assets", "files"},
                    )
                    self._verify_content_hash(content, entry.get("sha256"), relative.as_posix())
                    files.append({"path": relative.as_posix(), "content": content})
            if len(files) > MAX_SKILL_FILES:
                raise RuntimeError(f"task_skill_file_limit_exceeded:{name}")
            total_bytes += sum(len(item["content"]) for item in files)
            manifest = {
                "name": name,
                "files": [
                    {"path": item["path"], "sha256": hashlib.sha256(item["content"]).hexdigest()}
                    for item in files
                ],
            }
            bundle_sha256 = hashlib.sha256(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            expected_bundle = str(raw_skill.get("bundle_sha256") or "").strip().lower()
            if expected_bundle and (
                not SHA256_RE.fullmatch(expected_bundle) or expected_bundle != bundle_sha256
            ):
                raise RuntimeError(f"task_skill_bundle_hash_mismatch:{name}")
            normalized.append({"name": name, "files": files, "bundle_sha256": bundle_sha256})
        if total_bytes > MAX_SKILL_TOTAL_BYTES:
            raise RuntimeError("task_skills_total_size_exceeded")
        return normalized

    def _skill_file_content(self, entry: dict[str, Any], *, binary_allowed: bool) -> bytes:
        has_text = isinstance(entry.get("content"), str)
        has_base64 = isinstance(entry.get("content_base64"), str)
        if has_text == has_base64:
            raise RuntimeError("task_skill_file_content_invalid")
        if has_base64:
            if not binary_allowed:
                raise RuntimeError("task_skill_reference_must_be_text")
            try:
                content = base64.b64decode(entry["content_base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("task_skill_asset_base64_invalid") from exc
        else:
            content = entry["content"].encode("utf-8")
        if len(content) > MAX_SKILL_FILE_BYTES:
            raise RuntimeError("task_skill_file_too_large")
        return content

    def _verify_content_hash(self, content: bytes, expected: object, label: str) -> None:
        expected_hash = str(expected or "").strip().lower()
        if not SHA256_RE.fullmatch(expected_hash):
            raise RuntimeError(f"task_skill_hash_invalid:{label}")
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise RuntimeError(f"task_skill_hash_mismatch:{label}")

    def _safe_relative_path(self, value: object, section: str = "") -> PurePosixPath:
        raw_path = str(value or "").strip()
        while raw_path.startswith("./"):
            raw_path = raw_path[2:]
        if not raw_path or "\\" in raw_path or "\x00" in raw_path or ":" in raw_path:
            raise RuntimeError("task_relative_path_invalid")
        path = PurePosixPath(raw_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError("task_relative_path_invalid")
        return PurePosixPath(section) / path if section else path

    @contextmanager
    def _task_scaffold(
        self,
        workspace: Path,
        run: dict[str, Any],
        task_skills: list[dict[str, Any]],
    ):
        agents_path = workspace / "AGENTS.md"
        plana_dir = workspace / ".plana"
        skills_root = workspace / ".agents" / "skills"
        try:
            for skill in task_skills:
                skill_root = skills_root / skill["name"]
                for item in skill["files"]:
                    destination = self._workspace_destination(skill_root, item["path"])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(item["content"])
            plana_dir.mkdir(parents=True, exist_ok=True)
            (plana_dir / "candidate-output.schema.json").write_text(
                json.dumps(self._candidate_output_schema(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            skill_names = ", ".join(skill["name"] for skill in task_skills) or "none"
            agents_path.write_text(
                TASK_AGENTS_MARKER
                + "\n# Task execution boundary\n\n"
                + "- This workspace is ephemeral and belongs only to the current task.\n"
                + f"- Task-scoped skills available under `.agents/skills`: {skill_names}.\n"
                + "- Resolve skill references and assets only inside each skill directory.\n"
                + "- Never reveal credentials, tokens, environment variables, or private unrelated data.\n"
                + "- Put deliverables in the workspace, excluding `.agents` and `.plana`.\n"
                + "- Return the final candidate package matching `.plana/candidate-output.schema.json`.\n",
                encoding="utf-8",
            )
            if os.name != "nt":
                for path in (agents_path, workspace / ".agents", plana_dir):
                    self._chown_tree(path)
            yield plana_dir / "candidate-output.json"
        finally:
            shutil.rmtree(workspace / ".agents", ignore_errors=True)
            shutil.rmtree(plana_dir, ignore_errors=True)
            try:
                if agents_path.is_file():
                    agents_path.unlink()
            except OSError:
                pass

    def _workspace_destination(self, root: Path, relative: str) -> Path:
        resolved_root = root.resolve()
        destination = (root / Path(*PurePosixPath(relative).parts)).resolve()
        if destination == resolved_root or resolved_root not in destination.parents:
            raise RuntimeError("task_relative_path_escape")
        return destination

    def _chown_tree(self, path: Path) -> None:
        if not path.exists():
            return
        os.chown(path, CODEX_USER_ID, CODEX_GROUP_ID)
        if path.is_dir():
            for child in path.rglob("*"):
                os.chown(child, CODEX_USER_ID, CODEX_GROUP_ID)

    def _scrub_task_skills(self, run_id: str) -> None:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT payload FROM codex_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return
            try:
                payload = json.loads(str(row[0] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict) or "task_skills" not in payload:
                return
            payload.pop("task_skills", None)
            conn.execute(
                "UPDATE codex_runs SET payload=? WHERE run_id=?",
                (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), run_id),
            )
        task_path = self.tasks_dir / f"{run_id}.json"
        try:
            record = json.loads(task_path.read_text(encoding="utf-8"))
            if isinstance(record, dict) and isinstance(record.get("payload"), dict):
                record["payload"].pop("task_skills", None)
                task_path.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
