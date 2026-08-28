from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import signal
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from plana_codex_runner_output import MAX_CANDIDATE_OUTPUT_BYTES, RunnerOutputMixin
    from plana_codex_runner_skills import CODEX_GROUP_ID, CODEX_USER_ID, RunnerSkillMixin
except ModuleNotFoundError:
    from .plana_codex_runner_output import MAX_CANDIDATE_OUTPUT_BYTES, RunnerOutputMixin
    from .plana_codex_runner_skills import CODEX_GROUP_ID, CODEX_USER_ID, RunnerSkillMixin

LANES = ("interactive", "long", "high_isolation", "import")
MAX_ARTIFACTS = 64
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class RunnerExecutionMixin(RunnerSkillMixin, RunnerOutputMixin):
    def _execute_codex(self, run: dict[str, Any]) -> None:
        payload = run["payload"]
        if not self.ready:
            raise RuntimeError("codex_runtime_not_ready")
        query = str(payload.get("text") or payload.get("title") or "").strip()
        if not query:
            raise RuntimeError("codex_query_missing")
        service_refs = self._validated_service_refs(payload)
        started_at = int(time.time())
        workspace = self.codex_workspaces_dir / run["run_id"]
        result_dir = self.results_dir / run["run_id"]
        self._prepare_directory(workspace, owner=True)
        self._prepare_directory(result_dir)
        task_skills = self._validated_task_skills(payload)
        with self._task_scaffold(workspace, run, task_skills) as final_path:
            self._execute_codex_scoped(
                run,
                query=query,
                service_refs=service_refs,
                started_at=started_at,
                workspace=workspace,
                result_dir=result_dir,
                final_path=final_path,
            )

    def _execute_codex_scoped(
        self,
        run: dict[str, Any],
        *,
        query: str,
        service_refs: list[str],
        started_at: int,
        workspace: Path,
        result_dir: Path,
        final_path: Path,
    ) -> None:
        payload = run["payload"]
        selected_timeout = self.timeout_for_lane(run["lane"])
        selected_model = ""
        summary = ""
        structured: dict[str, Any] = {}
        failures: list[str] = []
        models = [self.codex_model, *self.codex_fallback_models]
        for attempt, model in enumerate(models, start=1):
            if final_path.exists():
                final_path.unlink()
            prompt = self._codex_prompt(run, query, service_refs)
            command = [
                str(self.setpriv_executable),
                f"--reuid={CODEX_USER_ID}",
                f"--regid={CODEX_GROUP_ID}",
                "--init-groups",
                "--",
                str(self.codex_executable),
                "exec",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                "--json",
                "--ephemeral",
                "-m",
                model,
                "-C",
                str(workspace),
                "-o",
                str(final_path),
                "--output-schema",
                str(workspace / ".plana" / "candidate-output.schema.json"),
                "-",
            ]
            process = subprocess.Popen(
                command,
                cwd=str(workspace),
                env=self._codex_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name != "nt",
            )
            with self.lock:
                self.processes[run["run_id"]] = process
            timed_out = False
            try:
                try:
                    stdout, stderr = process.communicate(input=prompt, timeout=selected_timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    self._terminate_process(process)
                    stdout, stderr = process.communicate()
            finally:
                with self.lock:
                    self.processes.pop(run["run_id"], None)
            safe_model = "".join(char if char.isalnum() else "-" for char in model).strip("-")
            (workspace / f"events-{attempt}-{safe_model}.jsonl").write_text(
                self._redact_sensitive(stdout or ""), encoding="utf-8"
            )
            (workspace / f"stderr-{attempt}-{safe_model}.txt").write_text(
                self._redact_sensitive(stderr or ""), encoding="utf-8"
            )
            if self._run_status(run["run_id"]) in {"cancelling", "cancelled"}:
                self._copy_workspace_artifacts(workspace, result_dir, started_at)
                result = self._cancelled_result(
                    run["run_id"],
                    request_id=run["request_id"],
                    lane=run["lane"],
                    payload=payload,
                    termination="terminated_process_group",
                )
                self._finish(run["run_id"], "cancelled", result=result)
                self._send_callback(payload, result)
                return
            if not timed_out and process.returncode == 0:
                try:
                    summary, structured = self._read_candidate_output(final_path)
                except RuntimeError as exc:
                    failures.append(f"{model}:{exc}")
                if summary and structured:
                    selected_model = model
                    break
            detail = f"timeout_{selected_timeout}s" if timed_out else self._last_codex_error(stderr, stdout)
            failures.append(f"{model}:{detail}")
        if not summary:
            raise RuntimeError(f"codex_models_failed:{' | '.join(failures)[-450:]}")
        self._copy_workspace_artifacts(workspace, result_dir, started_at)
        summary = summary[:6000]
        if not any(path.is_file() for path in result_dir.rglob("*")):
            (result_dir / "result-summary.txt").write_text(summary, encoding="utf-8")
        structured = self._sanitize_structure(structured)
        if len(json.dumps(structured, ensure_ascii=False).encode("utf-8")) > MAX_CANDIDATE_OUTPUT_BYTES:
            raise RuntimeError("candidate_output_too_large")
        finished_at = int(time.time())
        result = {
            "request_id": run["request_id"],
            "runner_run_id": run["run_id"],
            "run_id": run["run_id"],
            "scope_id": payload.get("scope_id", "global"),
            "actor_id": payload.get("actor_id", "codex_runner"),
            "lane": run["lane"],
            "success": True,
            "status": "succeeded",
            "result_summary": summary,
            "structured_result": structured,
            "verification": structured.get("verification", {}),
            "learning_candidates": structured.get("learning_candidates", []),
            "engine": "codex",
            "model": selected_model,
            "execution_profile": payload.get("execution_profile", "default"),
            "profile_revision": payload.get("profile_revision", ""),
            "executes_tasks": True,
            "started_at": _iso(started_at),
            "finished_at": _iso(finished_at),
            "duration_seconds": max(0, finished_at - started_at),
            "service_refs": service_refs,
            "artifacts": self._result_artifacts(result_dir)[:32],
        }
        self._finish(run["run_id"], "succeeded", result=result)
        self._send_callback(payload, result)

    def _validated_service_refs(self, payload: dict[str, Any]) -> list[str]:
        requested = payload.get("service_refs") or []
        if isinstance(requested, str):
            requested = [requested]
        if not isinstance(requested, list):
            raise RuntimeError("service_refs_must_be_list")
        normalized: list[str] = []
        for raw_value in requested:
            service_ref = str(raw_value or "").strip()
            if not service_ref:
                continue
            if service_ref not in self.service_toolsets:
                raise RuntimeError(f"service_ref_not_allowed:{service_ref}")
            if service_ref not in normalized:
                normalized.append(service_ref)
        return normalized

    def _codex_prompt(self, run: dict[str, Any], query: str, service_refs: list[str]) -> str:
        payload = run["payload"]
        context = {
            "request_id": run["request_id"],
            "run_id": run["run_id"],
            "lane": run["lane"],
            "scope_id": payload.get("scope_id", "global"),
            "service_refs": service_refs,
            "expected_artifacts": payload.get("expected_artifacts") or payload.get("artifacts") or [],
            "task_skills": [skill["name"] for skill in self._validated_task_skills(payload)],
            "candidate_output_schema": "plana.codex.candidate-output.v1",
            "execution_bundle": payload.get("execution_bundle") or {},
        }
        return (
            "You are the Plana production execution worker. Complete the task autonomously. "
            "Work inside the current workspace whenever possible. Put every deliverable that "
            "must be returned to Core in the current workspace. Verify your work before finishing. "
            "Do not reveal credentials, tokens, environment secrets, or unrelated private data. "
            "Your final response must exactly match the provided output schema. Return only "
            "the structured candidate package; use an empty learning_candidates list and null "
            "capability_candidate when none apply. For a capability candidate, write the full "
            "plana.capability.candidate.v1 manifest to a workspace artifact and return an object "
            "with manifest_path plus the exact manifest_json string; its status must remain "
            "quarantined for Core review. Every verification object must include passed, checks, "
            "and risk_reasons.\n\n"
            f"Execution context:\n{json.dumps(context, ensure_ascii=False)}\n\nTask:\n{query}"
        )

    def _codex_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._read_secret_env(self.codex_env_file))
        env.update({
            "HOME": str(self.codex_home),
            "CODEX_HOME": str(self.codex_home / ".codex"),
            "USER": "codex",
            "LOGNAME": "codex",
        })
        return env

    def _read_secret_env(self, path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip():
                values[key.strip()] = value.strip().strip('"').strip("'")
        if not values.get("NEWAPI_API_KEY"):
            raise RuntimeError("codex_api_key_missing")
        return values

    def _prepare_directory(self, path: Path, *, owner: bool = False) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if owner and os.name != "nt":
            os.chown(path, CODEX_USER_ID, CODEX_GROUP_ID)

    def _copy_workspace_artifacts(self, workspace: Path, result_dir: Path, started_at: int) -> None:
        copied = 0
        for source in sorted(workspace.rglob("*")):
            if copied >= MAX_ARTIFACTS or not source.is_file() or ".git" in source.parts:
                continue
            relative = source.relative_to(workspace)
            if (
                relative.parts[0] in {".agents", ".plana"}
                or relative.as_posix() == "AGENTS.md"
                or source.name.startswith("events-")
                or source.name.startswith("stderr-")
            ):
                continue
            try:
                stat = source.stat()
            except OSError:
                continue
            if stat.st_size > MAX_ARTIFACT_BYTES or int(stat.st_mtime) + 1 < started_at:
                continue
            destination = result_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1

    def _result_artifacts(self, result_dir: Path) -> list[dict[str, Any]]:
        return [self._artifact_metadata(path) for path in sorted(result_dir.rglob("*")) if path.is_file()][:MAX_ARTIFACTS]

    def _last_codex_message(self, stdout: str) -> str:
        messages: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = str(item.get("text") or "").strip()
                if text:
                    messages.append(text)
        return messages[-1] if messages else ""

    def _last_codex_error(self, stderr: str, stdout: str) -> str:
        combined = "\n".join(part for part in (stderr, stdout) if part).strip()
        lines = [line.strip() for line in combined.splitlines() if line.strip()]
        return self._redact_sensitive((lines[-1] if lines else "no_output")[-400:])

    def _artifact_metadata(self, path: Path) -> dict[str, Any]:
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "artifact_id": sha256,
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": sha256,
            "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        }

    def _run_status(self, run_id: str) -> str:
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT status FROM codex_runs WHERE run_id=?", (run_id,)).fetchone()
        return str(row[0] or "") if row else ""

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is not None:
                return
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                return

    def _cancelled_result(self, run_id: str, *, request_id: str, lane: str, payload: dict[str, Any], termination: str) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "runner_run_id": run_id,
            "run_id": run_id,
            "scope_id": payload.get("scope_id", "global"),
            "actor_id": payload.get("actor_id", "codex_runner"),
            "lane": lane,
            "success": False,
            "status": "cancelled",
            "result_summary": "Task cancelled by request.",
            "termination": termination,
            "engine": "codex",
            "model": self.codex_model,
            "executes_tasks": True,
            "finished_at": _iso(int(time.time())),
            "artifacts": [],
        }

    def _finish(self, run_id: str, status: str, *, result: dict[str, Any], error: str = "") -> None:
        now = int(time.time())
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE codex_runs
                SET status=?, error=?, terminal_at=?, heartbeat_at=?, lease_expires_at=0,
                    event_seq=event_seq+1, updated_at=?
                WHERE run_id=?
                """,
                (status, error[:500], now, now, now, run_id),
            )
        result.update(self._lifecycle_snapshot(run_id))
        serialized_result = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        with self.lock, self._connect() as conn:
            conn.execute(
                "UPDATE codex_runs SET result=? WHERE run_id=?",
                (serialized_result, run_id),
            )
        self._write_result_file(run_id, status, result, error)
        self._scrub_task_skills(run_id)

    def _write_result_file(self, run_id: str, status: str, result: dict[str, Any], error: str = "") -> None:
        (self.results_dir / f"{run_id}.json").write_text(
            json.dumps({"run_id": run_id, "status": status, "result": result, "error": error}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _send_callback(self, payload: dict[str, Any], result: dict[str, Any]) -> None:
        callback = str(payload.get("callback") or "").strip()
        if callback:
            self._post_callback(callback, result)

    def _post_callback(self, url: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_obj = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "X-Plana-Runner": "codex-runner"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=5) as response:
                if response.status >= 400:
                    self.last_error = f"callback_http_{response.status}"
        except (urllib.error.URLError, TimeoutError) as exc:
            self.last_error = f"callback_failed:{exc}"

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS codex_runs (
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL DEFAULT '',
                    lane TEXT NOT NULL DEFAULT 'interactive',
                    priority INTEGER NOT NULL DEFAULT 30,
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    payload TEXT NOT NULL DEFAULT '{}',
                    result TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_codex_lane_status
                    ON codex_runs(lane, status, priority, created_at);
                """
            )
            self._initialize_lifecycle_columns(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _lane(self, value: object) -> str:
        lane = str(value or "interactive").strip()
        return lane if lane in LANES else "interactive"


def _iso(timestamp: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _execution_error(exc: Exception, timeout_seconds: int) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"codex_timeout_{timeout_seconds}s"
    return " ".join(str(exc or "codex_execution_failed").split())[:500]


def _json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
