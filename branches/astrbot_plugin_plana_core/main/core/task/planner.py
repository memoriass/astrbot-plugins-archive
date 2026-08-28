from __future__ import annotations

from ..models import PlannerStep, TaskRecord
from ..safety import SafetyGate
from ..storage import PlanaStorage


class RulePlanner:
    def __init__(self, storage: PlanaStorage, safety_gate: SafetyGate):
        self.storage = storage
        self.safety_gate = safety_gate

    def plan_for_task(self, task: TaskRecord) -> list[PlannerStep]:
        existing = self.storage.list_planner_steps(task.id)
        if existing:
            return existing
        steps = self._rule_steps(task)
        for index, instruction in enumerate(steps, start=1):
            self.storage.add_planner_step(task.id, index, instruction, "pending")
        return self.storage.list_planner_steps(task.id)

    def _rule_steps(self, task: TaskRecord) -> list[str]:
        steps = ["确认任务目标与范围"]
        if self.safety_gate.requires_confirmation(task.risk_level):
            steps.append("等待用户确认高风险操作")
        if task.risk_level in {"high", "medium"}:
            steps.append("记录回滚路径与安全边界")
        steps.append("拆分最小可执行步骤")
        steps.append("执行后记录结果与后续动作")
        return steps
