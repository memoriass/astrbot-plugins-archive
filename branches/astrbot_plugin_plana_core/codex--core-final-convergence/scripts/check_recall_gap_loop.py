from __future__ import annotations

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
_ensure_package(f"{PKG}.memory", ROOT / "memory")
db_module = _load(f"{PKG}.plugin.db", ROOT / "plugin" / "db.py")
feedback_module = _load(f"{PKG}.memory.feedback", ROOT / "memory" / "feedback.py")
recall_gap_module = _load(
    f"{PKG}.memory.recall_gap",
    ROOT / "memory" / "recall_gap.py",
)
kernel_module = _load(f"{PKG}.memory.kernel", ROOT / "memory" / "kernel.py")

Database = db_module.Database
FeedbackQueue = feedback_module.FeedbackQueue
RecallGapTracker = recall_gap_module.RecallGapTracker
MemoryKernel = kernel_module.MemoryKernel


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, str, str]] = []

    def record(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: str,
        actor: str,
    ) -> None:
        self.events.append((action, resource_type, resource_id, detail, actor))


class FakeStorage:
    def __init__(self, db) -> None:
        self.db = db
        self.audit = FakeAudit()
        self.memories: list[dict[str, object]] = []
        self.semantics: list[dict[str, object]] = []

    def add_memory(
        self,
        scope: str,
        scope_id: str,
        kind: str,
        content: str,
        importance: float,
        source: str,
        **metadata,
    ) -> int:
        memory_id = len(self.memories) + 1
        self.memories.append(
            {
                "id": memory_id,
                "scope": scope,
                "scope_id": scope_id,
                "kind": kind,
                "content": content,
                "importance": importance,
                "source": source,
            }
        )
        return memory_id

    def upsert_semantic(
        self,
        scope_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
    ) -> None:
        self.semantics.append(
            {
                "scope_id": scope_id,
                "subject": subject,
                "predicate": predicate,
                "object_value": object_value,
                "confidence": confidence,
                "source": source,
            }
        )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="plana-recall-gap-"))
    try:
        db = Database(tmp / "plana.sqlite3")
        storage = FakeStorage(db)
        feedback = FeedbackQueue(db)
        tracker = RecallGapTracker(db)
        feedback.initialize()
        tracker.initialize()
        runtime = types.SimpleNamespace(
            storage=storage,
            feedback_queue=feedback,
            recall_gap_tracker=tracker,
            resolve_scope=lambda scope: "scope" if scope == "alias" else scope,
        )
        kernel = MemoryKernel(runtime)

        gap_id = tracker.record_gap("scope", "user:1", "vector recall not found")
        require(gap_id is not None and gap_id > 0, f"gap_id={gap_id}")
        duplicate_id = tracker.record_gap("scope", "user:1", "vector recall not found")
        require(duplicate_id == gap_id, f"duplicate_id={duplicate_id}")
        open_payload = kernel.recall_gaps("alias", "open", 5)
        require(open_payload["stats"]["open"] == 1, f"open_payload={open_payload}")

        empty = kernel.propose_recall_gap_memory("alias", gap_id, "")
        require(empty["error"] == "empty_content", f"empty={empty}")
        proposed = kernel.propose_recall_gap_memory(
            "alias",
            gap_id,
            "Vector recall plan should prefer atom candidates with fresh reinforcement.",
            kind="semantic_note",
            user_id="user:1",
        )
        require(proposed["queued"], f"proposed={proposed}")
        require(proposed["feedback_id"] > 0, f"proposed={proposed}")
        candidate = tracker.get(gap_id)
        require(candidate and candidate["status"] == "candidate", f"candidate={candidate}")
        duplicate_after_candidate = tracker.record_gap(
            "scope",
            "user:1",
            "vector recall not found",
        )
        require(
            duplicate_after_candidate == gap_id,
            f"duplicate_after_candidate={duplicate_after_candidate}",
        )

        updated = feedback.update_pending(
            storage,
            "scope",
            proposed["feedback_id"],
            content="Corrected vector recall guidance.",
            memory_kind="user_fact",
            actor="tester",
        )
        require(updated["ok"], f"updated={updated}")
        pending = feedback.pending_item("scope", proposed["feedback_id"])
        require(
            pending and pending["payload"]["content"] == "Corrected vector recall guidance.",
            f"pending={pending}",
        )
        require(
            pending["payload"]["kind"] == "user_fact",
            f"pending_kind={pending}",
        )

        processed = kernel.process_memory_feedback_item(
            "alias",
            proposed["feedback_id"],
            actor="tester",
        )
        require(processed["ok"], f"processed={processed}")
        require(processed["stats"]["processed"] == 1, f"processed={processed}")
        require(processed["stats"]["created"] == 1, f"processed={processed}")
        require(processed["recall_gap_resolved"] == [gap_id], f"processed={processed}")
        resolved = tracker.get(gap_id)
        require(resolved and resolved["status"] == "resolved", f"resolved={resolved}")
        require(storage.memories and storage.semantics, "memory_write_missing")
        require(storage.audit.events, "audit_missing")
        dismissed_id = feedback.submit_new_memory(
            "scope",
            "user:1",
            "This draft should be dismissed.",
            "semantic_note",
        )
        require(dismissed_id is not None, "dismissed_feedback_missing")
        dismissed = feedback.dismiss_pending(
            storage,
            "scope",
            dismissed_id,
            actor="tester",
        )
        require(dismissed["ok"], f"dismissed={dismissed}")
        require(
            feedback.pending_item("scope", dismissed_id) is None,
            "dismissed_feedback_still_pending",
        )
        require(not feedback.pending("scope", 5), "pending_feedback_not_empty")
        print("recall_gap_loop_check=ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
