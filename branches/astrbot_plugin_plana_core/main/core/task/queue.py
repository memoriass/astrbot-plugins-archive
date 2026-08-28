from __future__ import annotations

import re

from ..models import TaskRecord
from ..safety import SafetyGate
from ..storage import PlanaStorage


class TaskQueue:
    def __init__(self, storage: PlanaStorage, safety_gate: SafetyGate):
        self.storage = storage
        self.safety_gate = safety_gate

    def add(
        self,
        scope_id: str,
        owner_id: str,
        objective: str,
    ) -> TaskRecord | None:
        text = self._clean_objective(objective)
        if not text:
            return None
        risk_level = self.safety_gate.assess(text)
        status = self.safety_gate.initial_status(risk_level)
        return self.storage.add_task(scope_id, owner_id, text, status, risk_level)

    def list(self, scope_id: str, limit: int) -> list[TaskRecord]:
        return self.storage.list_tasks(scope_id, limit)

    def done(self, scope_id: str, task_id: int) -> TaskRecord | None:
        task = self.storage.get_task(scope_id, task_id)
        if task is None:
            return None
        self.storage.update_task_status(scope_id, task_id, "done")
        return self.storage.get_task(scope_id, task_id)

    def cancel(self, scope_id: str, task_id: int) -> TaskRecord | None:
        task = self.storage.get_task(scope_id, task_id)
        if task is None:
            return None
        self.storage.update_task_status(scope_id, task_id, "cancelled")
        return self.storage.get_task(scope_id, task_id)

    def _clean_objective(self, objective: str) -> str:
        text = " ".join(objective.replace("\n", " ").split())
        text = re.sub(
            r"(?i)(token|password|credential|secret|key)=\S+",
            r"\1=<redacted>",
            text,
        )
        text = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1<redacted>",
            text,
        )
        text = re.sub(r"([A-Za-z]:\\[^ \t]+|/[^\s]+)", "<path>", text)
        return text[:600]
