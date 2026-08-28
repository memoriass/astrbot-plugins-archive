from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from plana_codex_runner_shim import InvalidTaskPayloadError, RunnerState


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def expect_error(action, expected: str) -> None:
    try:
        action()
    except (RuntimeError, InvalidTaskPayloadError) as exc:
        assert expected in str(exc), (expected, str(exc))
    else:
        raise AssertionError(f"expected_error:{expected}")


def build_state(root: Path) -> RunnerState:
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
    os.environ.update(
        {
            "PLANA_CODEX_EXECUTABLE": str(executable),
            "PLANA_CODEX_HOME": str(codex_home),
            "PLANA_CODEX_ENV_FILE": str(env_file),
            "PLANA_CODEX_WORKSPACES": str(workspaces),
            "PLANA_SETPRIV_EXECUTABLE": str(setpriv),
        }
    )
    return RunnerState(
        token="",
        data_dir=root / "data",
        allowed_clients=("127.0.0.1",),
        timeout_seconds=30,
        toolsets="safe",
        worker_counts={"interactive": 1, "long": 0, "high_isolation": 0, "import": 0},
    )


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="plana-codex-skill-"))
    previous = dict(os.environ)
    try:
        state = build_state(root)
        skill_md = b"---\nname: demo-skill\ndescription: test\n---\nUse references/guide.md.\n"
        reference = b"bounded reference\n"
        asset = b"\x00task-asset\xff"
        payload = {
            "request_id": "skill-check",
            "text": "test task skill",
            "task_skills": [
                {
                    "name": "demo-skill",
                    "skill_md": skill_md.decode("utf-8"),
                    "sha256": digest(skill_md),
                    "references": [
                        {"path": "guide.md", "content": reference.decode("utf-8"), "sha256": digest(reference)}
                    ],
                    "assets": [
                        {"path": "sample.bin", "content_base64": base64.b64encode(asset).decode("ascii"), "sha256": digest(asset)}
                    ],
                }
            ],
        }
        normalized = state._validated_task_skills(payload)
        assert normalized[0]["name"] == "demo-skill"
        workspace = state.codex_workspaces_dir / "materialize-check"
        workspace.mkdir()
        run = {"run_id": "materialize-check", "request_id": "skill-check", "lane": "interactive", "payload": payload}
        with state._task_scaffold(workspace, run, normalized) as candidate_path:
            skill_root = workspace / ".agents" / "skills" / "demo-skill"
            assert (skill_root / "SKILL.md").read_bytes() == skill_md
            assert (skill_root / "references" / "guide.md").read_bytes() == reference
            assert (skill_root / "assets" / "sample.bin").read_bytes() == asset
            assert "plana-task-scoped-agents-v1" in (workspace / "AGENTS.md").read_text(encoding="utf-8")
            schema = json.loads((workspace / ".plana" / "candidate-output.schema.json").read_text(encoding="utf-8"))
            assert schema["additionalProperties"] is False
            (workspace / "report.md").write_text("report", encoding="utf-8")
            candidate_path.write_text(
                json.dumps(
                    {
                        "schema_version": "plana.codex.candidate-output.v1",
                        "status": "succeeded",
                        "result_summary": "done api_key=do-not-return",
                        "artifacts": [{"path": "report.md", "description": "report"}],
                        "verification": {
                            "passed": True,
                            "checks": ["unit"],
                            "risk_reasons": [],
                        },
                        "learning_candidates": [],
                        "capability_candidate": None,
                    }
                ),
                encoding="utf-8",
            )
            summary, candidate = state._read_candidate_output(candidate_path)
            assert summary == "done [REDACTED]"
            assert candidate["verification"]["passed"] is True
        assert not (workspace / ".agents").exists()
        assert not (workspace / ".plana").exists()
        assert not (workspace / "AGENTS.md").exists()

        bad_hash = json.loads(json.dumps(payload))
        bad_hash["task_skills"][0]["sha256"] = "0" * 64
        expect_error(lambda: state._validated_task_skills(bad_hash), "task_skill_hash_mismatch")
        for bad_path in ("../escape.md", "/absolute.md", "C:/drive.md", "nested\\escape.md"):
            traversal = json.loads(json.dumps(payload))
            traversal["task_skills"][0]["references"][0]["path"] = bad_path
            expect_error(lambda traversal=traversal: state._validated_task_skills(traversal), "task_relative_path_invalid")

        invalid_candidate = workspace / "invalid.json"
        invalid_candidate.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        expect_error(lambda: state._read_candidate_output(invalid_candidate), "candidate_output_keys_invalid")

        run_id, _ = state.enqueue(payload)
        with sqlite3.connect(state.db_path) as conn:
            stored = json.loads(conn.execute("SELECT payload FROM codex_runs WHERE run_id=?", (run_id,)).fetchone()[0])
        assert stored["task_skills"]
        state._scrub_task_skills(run_id)
        with sqlite3.connect(state.db_path) as conn:
            scrubbed = json.loads(conn.execute("SELECT payload FROM codex_runs WHERE run_id=?", (run_id,)).fetchone()[0])
        assert "task_skills" not in scrubbed
        task_record = json.loads((state.tasks_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        assert "task_skills" not in task_record["payload"]
        expect_error(lambda: state.enqueue(bad_hash), "task_skill_hash_mismatch")
    finally:
        os.environ.clear()
        os.environ.update(previous)
    print("codex_skill_materialization_check=ok")


if __name__ == "__main__":
    main()
