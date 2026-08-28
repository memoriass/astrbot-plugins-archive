from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from plana_codex_runner_shim import InvalidTaskPayloadError, RunnerState


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="plana-codex-runner-"))
    codex_home = root / "codex-home"
    (codex_home / ".codex").mkdir(parents=True)
    (codex_home / ".codex" / "config.toml").write_text('model = "test"\n', encoding="utf-8")
    workspaces = root / "workspaces"
    workspaces.mkdir()
    env_file = root / "codex.env"
    env_file.write_text("NEWAPI_API_KEY=test-only\n", encoding="utf-8")
    executable = root / ("codex.cmd" if os.name == "nt" else "codex")
    executable.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    setpriv = root / ("setpriv.cmd" if os.name == "nt" else "setpriv")
    setpriv.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
    setpriv.chmod(0o755)
    previous = dict(os.environ)
    try:
        os.environ.update(
            {
                "PLANA_CODEX_EXECUTABLE": str(executable),
                "PLANA_CODEX_HOME": str(codex_home),
                "PLANA_CODEX_ENV_FILE": str(env_file),
                "PLANA_CODEX_WORKSPACES": str(workspaces),
                "PLANA_SETPRIV_EXECUTABLE": str(setpriv),
            }
        )
        state = RunnerState(
            token="",
            data_dir=root / "data",
            allowed_clients=("127.0.0.1",),
            timeout_seconds=30,
            toolsets="safe",
            worker_counts={"interactive": 1, "long": 0, "high_isolation": 0, "import": 0},
        )
        assert state.ready
        status = state.status()
        assert status["task_skill_contract"] == "plana.codex.task-skills.v1"
        assert status["candidate_output_schema"] == "plana.codex.candidate-output.v1"
        run_id, lane = state.enqueue({"request_id": "codex-check", "text": "test"})
        assert lane == "interactive"
        cancelled = state.cancel(run_id)
        assert cancelled["status"] == "cancelled"
        assert cancelled["event_seq"] == 1
        assert cancelled["cancel_requested_at"] > 0
        assert cancelled["cancel_acknowledged_at"] >= cancelled["cancel_requested_at"]
        assert cancelled["terminal_at"] >= cancelled["cancel_acknowledged_at"]
        with sqlite3.connect(state.db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM codex_runs").fetchone()[0] == 1
        try:
            state.enqueue({"text": "bad", "task_skills": "invalid"})
        except InvalidTaskPayloadError as exc:
            assert "task_skills_must_be_list" in str(exc)
        else:
            raise AssertionError("invalid_task_skills_were_accepted")
    finally:
        os.environ.clear()
        os.environ.update(previous)
    print("codex_runner_shim_check=ok")


if __name__ == "__main__":
    main()
