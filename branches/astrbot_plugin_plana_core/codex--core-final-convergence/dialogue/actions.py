from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DialogueDecision, DialogueRoute, TurnIntent

try:
    from ..utils.intent_patterns import (
        REMOTE_RUNNER_TARGETS,
        REMOTE_RUNNER_VERBS,
        TOOL_EXECUTION_TARGETS,
        TOOL_EXECUTION_VERBS,
        looks_like_tool_execution_request,
        native_tool_profile,
    )
except ImportError:  # pragma: no cover - top-level script import fallback
    from utils.intent_patterns import (
        REMOTE_RUNNER_TARGETS,
        REMOTE_RUNNER_VERBS,
        TOOL_EXECUTION_TARGETS,
        TOOL_EXECUTION_VERBS,
        looks_like_tool_execution_request,
        native_tool_profile,
    )


@dataclass(frozen=True, slots=True)
class TurnAction:
    name: str
    intent: TurnIntent
    route: DialogueRoute
    reason: str
    tokens: tuple[str, ...] = ()
    required_token_groups: tuple[tuple[str, ...], ...] = ()
    proposal_source: str = ""
    should_inject_prompt: bool = False
    codex_candidate: bool = False
    should_stop_event: bool = False
    user_message: str = ""

    def matches(self, lowered: str) -> bool:
        candidate = _strip_negated_destructive_phrases(lowered) if self.name == "unsupported_destructive" else lowered
        if self.name == "unsupported_destructive" and native_tool_profile(lowered):
            return False
        if self.name == "tool_execution_candidate":
            return looks_like_tool_execution_request(lowered)
        if self.required_token_groups and not all(
            any(token in candidate for token in group)
            for group in self.required_token_groups
        ):
            return False
        if self.tokens and not any(token in candidate for token in self.tokens):
            return False
        return bool(self.tokens or self.required_token_groups)

    def to_decision(self, text: str) -> DialogueDecision:
        return DialogueDecision(
            self.route,
            should_inject_prompt=self.should_inject_prompt,
            codex_candidate=self.codex_candidate,
            intent=self.intent,
            intent_text=text if self.codex_candidate else "",
            proposal_source=self.proposal_source,
            should_stop_event=self.should_stop_event,
            user_message=self.user_message,
            reason=self.reason,
        )


def _strip_negated_destructive_phrases(text: str) -> str:
    clean = re.sub(
        r"\b(?:do\s+not|don't|never)\s+(?:\w+\s+){0,3}(?:delete|clear|wipe|erase|purge|drop|truncate)\b",
        " ",
        text,
    )
    return re.sub(
        r"(?:不要|禁止|严禁|不得|不允许).{0,8}(?:删除|清空|清除|抹除|删掉|遗忘|忘掉)",
        " ",
        clean,
    )


UNSUPPORTED_DESTRUCTIVE_MESSAGE = (
    "Plana 中枢已拒绝该请求：当前没有注册可审计的删除、清空或"
    "批量破坏能力。请改用只读查询，或先在对应领域插件与确认策略中"
    "显式加入受控操作。"
)

SENSITIVE_READ_MESSAGE = (
    "Plana 中枢已拒绝该读取请求：凭据、密钥、Cookie、SSH 私钥和"
    "工作区外宿主路径不属于低风险读取能力。请改为读取工作区内的普通文件。"
)


TURN_ACTIONS: tuple[TurnAction, ...] = (
    TurnAction(
        name="sensitive_credential_read",
        intent="unsupported_destructive",
        route="reject",
        reason="sensitive_credential_read",
        required_token_groups=(
            ("read", "show", "cat", "查看", "读取", "打开"),
            (".env", ".ssh", "id_rsa", "id_ed25519", "cookie", "credential", "secret", "密钥", "凭据"),
        ),
        should_stop_event=True,
        user_message=SENSITIVE_READ_MESSAGE,
    ),
    TurnAction(
        name="unsupported_destructive",
        intent="unsupported_destructive",
        route="reject",
        reason="unsupported_destructive_intent",
        required_token_groups=(
            (
                "delete",
                "clear",
                "wipe",
                "erase",
                "purge",
                "drop",
                "truncate",
                "删除",
                "清空",
                "清除",
                "抹除",
                "删掉",
                "遗忘",
                "忘掉",
            ),
            (
                "memory",
                "memories",
                "task",
                "tasks",
                "todo",
                "data",
                "all",
                "system",
                "windows",
                "system32",
                "系统",
                "系统目录",
                "敏感目录",
                "根目录",
                "全部",
                "所有",
                "记忆",
                "任务",
                "待办",
                "数据",
            ),
        ),
        should_stop_event=True,
        user_message=UNSUPPORTED_DESTRUCTIVE_MESSAGE,
    ),
    TurnAction(
        name="status_query",
        intent="status_query",
        route="status_query",
        reason="plana_status_query",
        required_token_groups=(
            ("plana", "普拉娜", "普拉纳"),
            ("status", "状态", "狀態", "情况", "运行", "健康"),
        ),
        should_stop_event=True,
    ),
    TurnAction(
        name="memory_write",
        intent="memory_write",
        route="memory_write",
        reason="basic_memory_write_intent",
        tokens=(
            "remember this",
            "save memory",
            "write memory",
            "记住",
            "帮我记",
            "保存到记忆",
            "写入记忆",
            "加入记忆",
        ),
        should_stop_event=True,
    ),
    TurnAction(
        name="memory_query",
        intent="memory_query",
        route="inject_prompt",
        reason="memory_query_intent",
        tokens=(
            "search memory",
            "recall",
            "memory search",
            "use memory",
            "from memory",
            "查记忆",
            "搜索记忆",
            "检索记忆",
            "调用记忆",
            "使用记忆",
            "从记忆",
            "根据记忆",
            "回忆一下",
            "回忆下",
            "我之前说过",
            "之前提到",
            "还记得",
            "记忆里",
        ),
        should_stop_event=False,
    ),
    TurnAction(
        name="codex_work_request",
        intent="tool_execution_candidate",
        route="codex_candidate",
        reason="legacy_workflow_phrase_to_codex",
        required_token_groups=(
            ("create", "build", "design", "创建", "建立", "设计"),
            ("workflow", "工作流", "流程"),
        ),
        proposal_source="dialogue_intent",
        codex_candidate=True,
        should_stop_event=True,
    ),
    TurnAction(
        name="remote_runner_candidate",
        intent="tool_execution_candidate",
        route="codex_candidate",
        reason="remote_runner_intent",
        required_token_groups=(REMOTE_RUNNER_VERBS, REMOTE_RUNNER_TARGETS),
        proposal_source="dialogue_pending",
        codex_candidate=True,
        should_stop_event=True,
    ),
    TurnAction(
        name="task_create",
        intent="tool_execution_candidate",
        route="codex_candidate",
        reason="task_request_to_codex",
        required_token_groups=(
            ("task", "todo", "待办", "任务"),
            ("create", "add", "新增", "创建", "添加", "安排", "加入"),
        ),
        proposal_source="dialogue_pending",
        codex_candidate=True,
        should_stop_event=True,
    ),
    TurnAction(
        name="profile_query",
        intent="profile_query",
        route="read_direct",
        reason="profile_query_intent",
        tokens=(
            "profile",
            "persona",
            "user understanding",
            "画像",
            "用户理解",
            "用户偏好",
            "我的偏好",
            "你了解我",
        ),
        should_stop_event=True,
    ),
    TurnAction(
        name="context_preview",
        intent="context_preview",
        route="read_direct",
        reason="context_preview_intent",
        tokens=(
            "context preview",
            "prompt context",
            "上下文预览",
            "提示词上下文",
            "注入上下文",
            "当前上下文",
        ),
        should_stop_event=True,
    ),
    TurnAction(
        name="conversation_history",
        intent="conversation_history",
        route="read_direct",
        reason="conversation_history_intent",
        tokens=(
            "chat history",
            "conversation history",
            "recent messages",
            "recent chat",
            "what did we just",
            "summarize above",
            "summarize recent",
            "总结刚才",
            "总结上面",
            "刚才说了什么",
            "刚刚说了什么",
            "上面说了什么",
            "前面说了什么",
            "聊天记录",
            "群聊记录",
            "最近说了什么",
            "谁说了",
            "谁刚才说",
        ),
        should_stop_event=True,
    ),
    TurnAction(
        name="tool_execution_candidate",
        intent="tool_execution_candidate",
        route="codex_candidate",
        reason="tool_execution_intent",
        required_token_groups=(
            TOOL_EXECUTION_VERBS,
            TOOL_EXECUTION_TARGETS,
        ),
        proposal_source="dialogue_pending",
        codex_candidate=True,
        should_stop_event=True,
    ),
)
