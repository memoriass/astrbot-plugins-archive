from __future__ import annotations

import re
import secrets
import time
from typing import Any

from ..routing.commands import normalize_task_ref
from .sqlite_store import RuntimeStorageMixin


class PendingTaskStoreMixin(RuntimeStorageMixin):
    def _cleanup_pending_tasks(self) -> None:
        self.cleanup_runtime_store()

    def resolve_pending_task_id(self, task_ref: str, *, origin: str = "") -> tuple[str, list[str]]:
        self._cleanup_pending_tasks()
        ref = normalize_task_ref(task_ref)
        if not ref:
            return "", []
        store = self.runtime_store()
        if re.fullmatch(r"ani[0-9a-f]{8}", ref) and store.get_pending(ref):
            return ref, []

        matches: list[str] = []
        body_ref = ref.removeprefix("ani")
        for task_id, _task in store.list_pending(origin=origin):
            body = task_id.removeprefix("ani")
            if (
                task_id.startswith(ref)
                or task_id.endswith(ref)
                or body.startswith(ref)
                or body.endswith(ref)
                or (body_ref and (body.startswith(body_ref) or body.endswith(body_ref)))
            ):
                matches.append(task_id)
        if len(matches) == 1:
            return matches[0], []
        if len(matches) > 1:
            return "", sorted(matches)
        return "", []

    def create_pending_task(self, task: dict[str, Any]) -> str:
        self._cleanup_pending_tasks()
        task_id = str(task.get("task_id") or "").strip()
        store = self.runtime_store()
        if not task_id:
            while True:
                task_id = f"ani{secrets.token_hex(4)}"
                if not store.pending_exists(task_id):
                    break
        now = time.time()
        stored = dict(task)
        stored["task_id"] = task_id
        stored.setdefault("created_at", now)
        stored["expires_at"] = now + self.pending_task_ttl_seconds()
        store.set_pending(task_id, stored)
        return task_id

    def get_pending_task(self, task_id: str) -> dict[str, Any] | None:
        self._cleanup_pending_tasks()
        return self.runtime_store().get_pending(str(task_id or "").strip())

    def pop_pending_task(self, task_id: str) -> dict[str, Any] | None:
        self._cleanup_pending_tasks()
        return self.runtime_store().pop_pending(str(task_id or "").strip())

    def update_pending_task(
        self,
        task_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        self._cleanup_pending_tasks()
        return self.runtime_store().update_pending(str(task_id or "").strip(), updates)
