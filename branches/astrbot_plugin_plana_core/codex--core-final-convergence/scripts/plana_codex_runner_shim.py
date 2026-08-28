#!/usr/bin/env python3
"""Plana Codex Runner with persistent multi-lane queues.

The runner accepts bounded delegation payloads, persists them, returns 202
immediately, and executes them through the installed Codex CLI.
"""
from __future__ import annotations
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8766
DEFAULT_DATA_DIR = "/home/codex/data/runner"
DEFAULT_ALLOWED_CLIENTS = "127.0.0.1,::1,192.168.1.201"
DEFAULT_CODEX_EXECUTABLE = "/usr/bin/codex"
DEFAULT_CODEX_HOME = "/home/codex"
DEFAULT_CODEX_ENV_FILE = "/etc/plana-codex.env"
DEFAULT_CODEX_WORKSPACES = "/home/codex/workspaces"
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_FALLBACK_MODELS = "gpt-5.6-luna"
DEFAULT_SETPRIV_EXECUTABLE = "/usr/bin/setpriv"
LANES = ("interactive", "long", "high_isolation", "import")
DEFAULT_WORKER_COUNTS = {"interactive": 1, "long": 0, "high_isolation": 0, "import": 0}
MAX_BODY_BYTES = 512 * 1024
MAX_STORED_PAYLOAD_BYTES = MAX_BODY_BYTES
try:
    from plana_codex_runner_execution import (
        RunnerExecutionMixin, _execution_error, _iso, _json, _safe_int,
    )
except ModuleNotFoundError:
    from .plana_codex_runner_execution import (
        RunnerExecutionMixin, _execution_error, _iso, _json, _safe_int,
    )
try:
    from plana_codex_runner_lifecycle import RUNNER_LEASE_SECONDS, RunnerLifecycleMixin
except ModuleNotFoundError:
    from .plana_codex_runner_lifecycle import RUNNER_LEASE_SECONDS, RunnerLifecycleMixin


class LaneDisabledError(RuntimeError):
    def __init__(self, lane: str) -> None:
        super().__init__(f"lane_disabled:{lane}")
        self.lane = lane

class InvalidTaskPayloadError(ValueError):
    pass
class RunnerState(RunnerLifecycleMixin, RunnerExecutionMixin):
    def __init__(
        self,
        *,
        token: str,
        data_dir: Path,
        allowed_clients: tuple[str, ...],
        timeout_seconds: int,
        toolsets: str,
        worker_counts: dict[str, int],
        lane_toolsets: dict[str, str] | None = None,
        lane_timeouts: dict[str, int] | None = None,
        service_toolsets: dict[str, str] | None = None,
    ) -> None:
        self.token = token
        self.data_dir = data_dir
        self.allowed_clients = allowed_clients
        self.codex_executable = Path(os.getenv("PLANA_CODEX_EXECUTABLE", DEFAULT_CODEX_EXECUTABLE))
        self.codex_home = Path(os.getenv("PLANA_CODEX_HOME", DEFAULT_CODEX_HOME))
        self.codex_env_file = Path(os.getenv("PLANA_CODEX_ENV_FILE", DEFAULT_CODEX_ENV_FILE))
        self.codex_workspaces_dir = Path(os.getenv("PLANA_CODEX_WORKSPACES", DEFAULT_CODEX_WORKSPACES))
        self.codex_model = os.getenv("PLANA_CODEX_MODEL", DEFAULT_CODEX_MODEL).strip()
        self.codex_fallback_models = tuple(
            model.strip()
            for model in os.getenv("PLANA_CODEX_FALLBACK_MODELS", DEFAULT_CODEX_FALLBACK_MODELS).split(",")
            if model.strip() and model.strip() != self.codex_model
        )
        self.setpriv_executable = Path(os.getenv("PLANA_SETPRIV_EXECUTABLE", DEFAULT_SETPRIV_EXECUTABLE))
        self.timeout_seconds = max(10, min(int(timeout_seconds), 3600))
        self.toolsets = toolsets.strip()
        self.worker_counts = worker_counts
        self.lane_toolsets = {
            lane: str(value or "").strip()
            for lane, value in (lane_toolsets or {}).items()
            if lane in LANES and str(value or "").strip()
        }
        self.lane_timeouts = {
            lane: max(10, min(int(value), 3600))
            for lane, value in (lane_timeouts or {}).items()
            if lane in LANES
        }
        self.service_toolsets = {
            str(service_ref).strip(): str(value or "").strip()
            for service_ref, value in (service_toolsets or {}).items()
            if str(service_ref).strip() and str(value or "").strip()
        }
        self.tasks_dir = data_dir / "tasks"
        self.results_dir = data_dir / "results"
        self.db_path = data_dir / "runner.sqlite3"
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.workers: list[threading.Thread] = []
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.last_error = ""
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def start_workers(self) -> None:
        for lane, count in self.worker_counts.items():
            for index in range(count):
                worker = threading.Thread(
                    target=self._worker_loop,
                    args=(lane,),
                    name=f"plana-codex-{lane}-{index + 1}",
                    daemon=True,
                )
                worker.start()
                self.workers.append(worker)

    def enqueue(self, payload: dict[str, Any]) -> tuple[str, str]:
        lane = self._lane(payload.get("lane"))
        if not self.lane_enabled(lane):
            raise LaneDisabledError(lane)
        try:
            self._validated_task_skills(payload)
        except RuntimeError as exc:
            raise InvalidTaskPayloadError(str(exc)) from exc
        serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized_payload.encode("utf-8")) > MAX_STORED_PAYLOAD_BYTES:
            raise InvalidTaskPayloadError("task_payload_too_large")
        run_id = f"plana-{int(time.time())}-{uuid.uuid4().hex[:12]}"
        now = int(time.time())
        request_id = str(payload.get("request_id") or "")
        title = str(payload.get("title") or payload.get("text") or "")[:180]
        record = {
            "run_id": run_id,
            "request_id": request_id,
            "lane": lane,
            "status": "queued",
            "payload": payload,
            "received_at": _iso(now),
            "executes_tasks": self.ready,
        }
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO codex_runs (
                    run_id, request_id, lane, priority, title, status, payload,
                    attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    request_id,
                    lane,
                    _safe_int(payload.get("priority"), 30),
                    title,
                    "queued",
                    serialized_payload,
                    0,
                    now,
                    now,
                ),
            )
        (self.tasks_dir / f"{run_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run_id, lane

    def lane_enabled(self, value: object) -> bool:
        lane = self._lane(value)
        return int(self.worker_counts.get(lane, 0) or 0) > 0

    def status(self) -> dict[str, Any]:
        with self.lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT lane, status, COUNT(*) FROM codex_runs GROUP BY lane, status"
            ).fetchall()
            recent_rows = conn.execute(
                """
                SELECT run_id, request_id, lane, status, title, error, updated_at,
                       attempt_id, attempts, event_seq, heartbeat_at, lease_expires_at
                FROM codex_runs
                ORDER BY updated_at DESC
                LIMIT 12
                """
            ).fetchall()
        lanes = {lane: {"queued": 0, "running": 0, "succeeded": 0, "failed": 0} for lane in LANES}
        for lane, status, count in rows:
            lanes.setdefault(str(lane), {})[str(status)] = int(count)
        return {
            "ok": True,
            "runner": "plana-codex-runner",
            "engine": "codex",
            "model": self.codex_model,
            "fallback_models": list(self.codex_fallback_models),
            "executes_tasks": self.ready,
            "codex_executable": str(self.codex_executable),
            "codex_home": str(self.codex_home),
            "timeout_seconds": self.timeout_seconds,
            "toolsets": self.toolsets,
            "lane_toolsets": dict(self.lane_toolsets),
            "lane_timeouts": dict(self.lane_timeouts),
            "service_refs": sorted(self.service_toolsets),
            "task_skill_contract": "plana.codex.task-skills.v1",
            "candidate_output_schema": "plana.codex.candidate-output.v1",
            "auth_model": "lan_allowlist" if not self.token else "bearer_or_lan_allowlist",
            "allowed_clients": list(self.allowed_clients),
            "workers": dict(self.worker_counts),
            "lanes": lanes,
            "last_error": self.last_error,
            "recent": [
                {
                    "run_id": row[0],
                    "request_id": row[1],
                    "lane": row[2],
                    "status": row[3],
                    "title": row[4],
                    "error": row[5],
                    "updated_at": row[6],
                    "attempt_id": row[7],
                    "attempt_no": row[8],
                    "event_seq": row[9],
                    "heartbeat_at": row[10],
                    "lease_expires_at": row[11],
                }
                for row in recent_rows
            ],
        }

    def result(self, run_id: str) -> dict[str, Any] | None:
        with self.lock, self._connect() as conn:
            row = conn.execute(
                """SELECT run_id, request_id, lane, status, title, result, error, updated_at,
                          attempt_id, attempts, event_seq, heartbeat_at, lease_expires_at,
                          cancel_requested_at, cancel_acknowledged_at, terminal_at
                   FROM codex_runs WHERE run_id=?""",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        result = _json(row[5]) or {"result_summary": row[6] or ""}
        defaults = {
            "request_id": row[1],
            "runner_run_id": row[0],
            "run_id": row[0],
            "lane": row[2],
            "status": row[3],
            "success": row[3] == "succeeded",
            "title": row[4],
            "updated_at": row[7],
            "attempt_id": row[8],
            "attempt_no": row[9],
            "event_seq": row[10],
            "heartbeat_at": row[11],
            "lease_expires_at": row[12],
            "cancel_requested_at": row[13],
            "cancel_acknowledged_at": row[14],
            "terminal_at": row[15],
        }
        for key, value in defaults.items():
            result.setdefault(key, value)
        return result

    def artifact(self, run_id: str, artifact_id: str) -> tuple[Path, dict[str, Any]] | None:
        result = self.result(str(run_id or "").strip())
        clean_artifact_id = str(artifact_id or "").strip()
        if not isinstance(result, dict) or not clean_artifact_id:
            return None
        artifacts = result.get("artifacts")
        if not isinstance(artifacts, list):
            return None
        allowed_roots = (self.results_dir.resolve(),)
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            stored_artifact_id = str(
                artifact.get("artifact_id") or artifact.get("sha256") or ""
            )
            if stored_artifact_id != clean_artifact_id:
                continue
            raw_path = str(artifact.get("path") or "").strip()
            if not raw_path:
                return None
            path = Path(raw_path).resolve()
            if not any(path == root or root in path.parents for root in allowed_roots):
                return None
            if not path.is_file():
                return None
            return path, artifact
        return None

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            return None
        now = int(time.time())
        with self.lock, self._connect() as conn:
            row = conn.execute(
                """SELECT request_id, lane, status, payload, event_seq, attempt_id, attempts
                   FROM codex_runs WHERE run_id=?""",
                (clean_run_id,),
            ).fetchone()
            if row is None:
                return None
            status = str(row[2] or "")
            if status in {"succeeded", "failed", "cancelled"}:
                return self.result(clean_run_id)
            payload = _json(row[3])
            if status == "queued":
                result = self._cancelled_result(
                    clean_run_id,
                    request_id=str(row[0] or ""),
                    lane=str(row[1] or "interactive"),
                    payload=payload,
                    termination="cancelled_before_start",
                )
                result.update(
                    {
                        "attempt_id": str(row[5] or ""),
                        "attempt_no": int(row[6] or 0),
                        "event_seq": int(row[4] or 0) + 1,
                        "heartbeat_at": now,
                        "lease_expires_at": 0,
                        "cancel_requested_at": now,
                        "cancel_acknowledged_at": now,
                        "terminal_at": now,
                    }
                )
                conn.execute(
                    """
                    UPDATE codex_runs
                    SET status='cancelled', result=?, error='',
                        cancel_requested_at=?, cancel_acknowledged_at=?, terminal_at=?,
                        heartbeat_at=?, lease_expires_at=0, event_seq=event_seq+1,
                        updated_at=?
                    WHERE run_id=? AND status='queued'
                    """,
                    (
                        json.dumps(result, ensure_ascii=False)[:16000],
                        now, now, now, now, now, clean_run_id,
                    ),
                )
                self._write_result_file(clean_run_id, "cancelled", result)
                self._scrub_task_skills(clean_run_id)
                return result
            conn.execute(
                """
                UPDATE codex_runs
                SET status='cancelling',
                    cancel_requested_at=COALESCE(NULLIF(cancel_requested_at, 0), ?),
                    cancel_acknowledged_at=?, heartbeat_at=?, lease_expires_at=?,
                    event_seq=event_seq+1, updated_at=?
                WHERE run_id=? AND status IN ('running', 'cancelling')
                """,
                (now, now, now, now + RUNNER_LEASE_SECONDS, now, clean_run_id),
            )
            process = self.processes.get(clean_run_id)
            if process is None:
                result = self._cancelled_result(
                    clean_run_id,
                    request_id=str(row[0] or ""),
                    lane=str(row[1] or "interactive"),
                    payload=payload,
                    termination="cancelled_after_runner_restart",
                )
                result.update(
                    {
                        "attempt_id": str(row[5] or ""),
                        "attempt_no": int(row[6] or 0),
                        "event_seq": int(row[4] or 0) + 2,
                        "heartbeat_at": now,
                        "lease_expires_at": 0,
                        "cancel_requested_at": now,
                        "cancel_acknowledged_at": now,
                        "terminal_at": now,
                    }
                )
                conn.execute(
                    """
                    UPDATE codex_runs
                    SET status='cancelled', result=?, error='', terminal_at=?,
                        heartbeat_at=?, lease_expires_at=0, event_seq=event_seq+1,
                        updated_at=?
                    WHERE run_id=? AND status='cancelling'
                    """,
                    (
                        json.dumps(result, ensure_ascii=False)[:16000],
                        now, now, now, clean_run_id,
                    ),
                )
                self._write_result_file(clean_run_id, "cancelled", result)
                self._scrub_task_skills(clean_run_id)
                return result
        if process is not None:
            self._terminate_process(process)
        result = self.result(clean_run_id)
        if result is not None:
            result["status"] = "cancelling"
            result["success"] = False
        return result

    def _worker_loop(self, lane: str) -> None:
        while not self.stop_event.is_set():
            run = self._claim_next(lane)
            if run is None:
                self.stop_event.wait(0.25)
                continue
            try:
                heartbeat_stop, heartbeat_worker = self._start_lifecycle_heartbeat(run["run_id"])
                try:
                    self._execute_codex(run)
                finally:
                    heartbeat_stop.set()
                    heartbeat_worker.join(timeout=1)
            except Exception as exc:  # noqa: BLE001
                error = _execution_error(exc, self.timeout_for_lane(run["lane"]))
                self.last_error = error
                finished_at = int(time.time())
                payload = run["payload"]
                result = {
                    "request_id": run["request_id"],
                    "runner_run_id": run["run_id"],
                    "run_id": run["run_id"],
                    "scope_id": payload.get("scope_id", "global"),
                    "actor_id": payload.get("actor_id", "codex_runner"),
                    "lane": run["lane"],
                    "success": False,
                    "status": "failed",
                    "result_summary": error,
                    "error": error,
                    "executes_tasks": True,
                    "finished_at": _iso(finished_at),
                    "artifacts": [],
                }
                self._finish(run["run_id"], "failed", error=error, result=result)
                callback = str(payload.get("callback") or "").strip()
                if callback:
                    self._post_callback(callback, result)

    def _claim_next(self, lane: str) -> dict[str, Any] | None:
        now = int(time.time())
        with self.lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, request_id, lane, title, payload, attempts
                FROM codex_runs
                WHERE lane=? AND status='queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (lane,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE codex_runs
                SET status='running', attempts=attempts+1, attempt_id=?,
                    event_seq=event_seq+1, heartbeat_at=?, lease_expires_at=?,
                    updated_at=?
                WHERE run_id=? AND status='queued'
                """,
                (
                    f"{row[0]}:attempt-{int(row[5] or 0) + 1}",
                    now,
                    now + RUNNER_LEASE_SECONDS,
                    now,
                    row[0],
                ),
            )
        return {
            "run_id": row[0],
            "request_id": row[1],
            "lane": row[2],
            "title": row[3],
            "payload": _json(row[4]),
            "attempts": int(row[5] or 0) + 1,
        }

    @property
    def ready(self) -> bool:
        return bool(
            self.codex_executable.is_file()
            and os.access(self.codex_executable, os.X_OK)
            and self.setpriv_executable.is_file()
            and os.access(self.setpriv_executable, os.X_OK)
            and (self.codex_home / ".codex" / "config.toml").is_file()
            and self.codex_env_file.is_file()
            and self.codex_env_file.stat().st_size > 0
            and self.codex_workspaces_dir.is_dir()
        )

    def timeout_for_lane(self, lane: str) -> int:
        return int(self.lane_timeouts.get(lane, self.timeout_seconds))
