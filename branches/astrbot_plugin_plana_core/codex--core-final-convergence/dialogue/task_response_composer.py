from __future__ import annotations

from typing import Any

from .remote_task import CodexDelegationResult


class TaskResponseComposer:
    """Keeps user-facing task replies conversational and recovery-oriented."""

    def with_recovery(
        self,
        reply: str,
        *,
        auto_confirm: bool,
        remote_result: CodexDelegationResult | None = None,
        max_recovery_steps: int = 2,
    ) -> str:
        text = str(reply or "")
        if not text:
            text = "Plana 任务没有返回可见结果；可以重试，或查看状态诊断。"
        if remote_result and remote_result.delegated:
            return f"{text}\n{remote_result.message}"
        if max_recovery_steps <= 0 or "下一步" in text:
            return text
        recovery = self.recovery_summary(text)
        if not recovery:
            return text
        prefix = "Plana 已尝试自动执行。" if auto_confirm else "Plana 已生成执行方案。"
        return f"{text}\n{prefix}\n下一步：{recovery}"

    def recovery_summary(self, text: str) -> str:
        lowered = text.lower()
        if "output clipped" in lowered or "裁剪" in text:
            return "输出已被裁剪，可要求继续展开关键部分。"
        if "error=" in lowered or "错误" in text or "未成功" in text:
            return "根据错误信息重试，或改用更明确的目标和范围。"
        return ""

    def remote_delegate_reply(self, result: CodexDelegationResult) -> str:
        if result.delegated:
            return result.message
        if result.error == "assistant_remote_runner_disabled":
            return "Codex Runner 未启用；复杂任务不会改走本地命令或旧工作流。"
        return result.message or f"Codex Runner 暂不可用：{result.error or result.status}"

    def route_trace_status(self, payload: dict[str, Any]) -> str:
        if payload.get("delegated"):
            return "remote_queued"
        if payload.get("error"):
            return "remote_unavailable"
        return "remote_skipped"
