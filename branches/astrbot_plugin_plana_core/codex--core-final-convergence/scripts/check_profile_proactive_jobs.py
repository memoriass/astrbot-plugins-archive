from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "astrbot_plugin_plana_core"


def _ensure_package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"load_failed={path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package(PKG, ROOT)
_ensure_package(f"{PKG}.plugin", ROOT / "plugin")
_ensure_package(f"{PKG}.identity", ROOT / "identity")
_ensure_package(f"{PKG}.proactive", ROOT / "proactive")
_ensure_package(f"{PKG}.jobs", ROOT / "jobs")
db_module = _load(f"{PKG}.plugin.db", ROOT / "plugin" / "db.py")
profile_module = _load(
    f"{PKG}.identity.profile_evidence",
    ROOT / "identity" / "profile_evidence.py",
)
queue_module = _load(f"{PKG}.proactive.queue", ROOT / "proactive" / "queue.py")
jobs_module = _load(f"{PKG}.jobs.manager", ROOT / "jobs" / "manager.py")

Database = db_module.Database
ProfileEvidenceStorage = profile_module.ProfileEvidenceStorage
ProactiveQueue = queue_module.ProactiveQueue
RuntimeJobManager = jobs_module.RuntimeJobManager


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


async def _check_jobs() -> None:
    calls = {"count": 0}

    async def handler() -> None:
        calls["count"] += 1

    manager = RuntimeJobManager()
    manager.register("unit", handler, interval_seconds=60)
    result = await manager.run_once("unit")
    status = manager.status()["unit"]
    require(result["ok"], f"job_result={result}")
    require(calls["count"] == 1 and status["run_count"] == 1, f"job_status={status}")
    await manager.stop_all()


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="plana-profile-proactive-"))
    try:
        db = Database(tmp / "plana.sqlite3")
        evidence = ProfileEvidenceStorage(db)
        evidence.initialize()
        evidence_id = evidence.record_evidence(
            scope_id="scope",
            user_id="user:1",
            kind="user_preference",
            subject="user:user:1",
            predicate="preference",
            object_value="precise plans",
            confidence=0.8,
            source="test",
            source_memory_id=42,
        )
        snapshot_id = evidence.snapshot(
            scope_id="scope",
            user_id="user:1",
            summary="nickname: tester",
            profile={"nickname": "tester"},
            semantic_count=1,
            relation_count=0,
            source="test",
        )
        require(evidence_id > 0 and snapshot_id > 0, "profile_ids_missing")
        require(evidence.recent_evidence("scope", "user:1", 1)[0]["source_memory_id"] == 42, "evidence")
        profile_source = (ROOT / "identity" / "profile_evidence.py").read_text(encoding="utf-8")
        require("profile_refresh_queue" not in profile_source, "legacy_refresh_queue_reactivated")

        queue = ProactiveQueue(db)
        queue.initialize()
        task_id = queue.enqueue_reminder(
            "scope",
            "user:1",
            "review the plan",
            delay_seconds=0,
            appointment=True,
        )
        require(task_id is not None, f"task_id={task_id}")
        ready = queue.poll_ready(limit=5)
        require(len(ready) == 1 and ready[0]["kind"] == "appointment", f"ready={ready}")
        require(queue.mark_delivered(int(task_id)), f"deliver={task_id}")
        asyncio.run(_check_jobs())
        print("profile_proactive_jobs_check=ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
