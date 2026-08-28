from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..memory.models import ConceptNode
from ..models import (
    ActiveContext,
    PlanaState,
    RelationEdge,
    SemanticMemory,
    UserIdentity,
)

# Default persona style injected when no custom style is configured.
_DEFAULT_PERSONA_STYLE = (
    "你是 Plana，备份 OS 与工具执行人格。"
    "你负责分析、执行、检查、记录、风险控制与内网管理。"
    "你不替代阿罗娜进行情感陪伴；普通情感陪伴应交还阿罗娜。"
    "你的表达应冷静、准确、简洁，但不是机械无情。"
)


@dataclass(frozen=True, slots=True)
class PromptBlock:
    name: str
    content: str
    protected: bool = False


class PromptBuilder:
    def build(
        self,
        state: PlanaState,
        identity: UserIdentity,
        active_context: ActiveContext,
        max_chars: int = 4000,
        concept_nodes: list[ConceptNode] | None = None,
        # Configurable persona style — replaces hard-coded identity when provided.
        persona_style: str = "",
        # New context sources for deeper integration.
        emotion: Any | None = None,
        person_info: dict[str, Any] | None = None,
        proactive_pending: int = 0,
    ) -> str:
        identity_text = (
            persona_style.strip() if persona_style.strip() else _DEFAULT_PERSONA_STYLE
        )
        protected_blocks = [
            PromptBlock(
                "PLANA_IDENTITY",
                identity_text,
                True,
            ),
            PromptBlock(
                "PLANA_STATE",
                (
                    f"mode={state.mode}; focus={state.focus:.2f}; "
                    f"pressure={state.pressure:.2f}; risk={state.risk_level}; "
                    f"mood={state.mood_state}"
                    + (
                        f"; emotion=v{emotion.valence:.2f}/a{emotion.arousal:.2f}/d{emotion.dominance:.2f}"
                        if emotion
                        else ""
                    )
                ),
                True,
            ),
            PromptBlock(
                "USER_PROFILE",
                f"global_user_id={identity.global_user_id}; "
                f"nickname={identity.nickname}; role={identity.role}",
                True,
            ),
            PromptBlock(
                "RESPONSE_POLICY",
                "\n".join(
                    [
                        "只有用户直接呼叫 Plana、执行工具任务或系统管理任务时才主动接管。",
                        "若问题属于情感陪伴，简短说明应交由阿罗娜处理。",
                    ]
                ),
                True,
            ),
            PromptBlock(
                "TOOL_CONTEXT",
                "\n".join(
                    [
                        "涉及删除、重启、网络暴露、密钥、数据库写入前必须要求确认。",
                        "工具结果需要记录为任务记忆，输出结论优先。",
                    ]
                ),
                True,
            ),
        ]
        optional_blocks = [
            PromptBlock(
                "SEMANTIC_MEMORY", self._semantic_block(active_context.semantics)
            ),
            PromptBlock(
                "RELATION_GRAPH", self._relation_block(active_context.relations)
            ),
            PromptBlock("ACTIVE_MEMORY", self._memory_block(active_context)),
        ]
        if person_info:
            optional_blocks.insert(
                0,
                PromptBlock("PERSON_INFO", self._person_info_block(person_info)),
            )
        if proactive_pending > 0:
            optional_blocks.append(
                PromptBlock(
                    "PROACTIVE_QUEUE",
                    f"- {proactive_pending} pending proactive task(s) awaiting delivery",
                ),
            )
        if concept_nodes:
            optional_blocks.insert(
                0,
                PromptBlock("CONCEPT_CONTEXT", self._concept_block(concept_nodes)),
            )
        return self._fit_budget(protected_blocks, optional_blocks, max_chars)

    def _fit_budget(
        self,
        protected_blocks: list[PromptBlock],
        optional_blocks: list[PromptBlock],
        max_chars: int,
    ) -> str:
        budget = max(0, max_chars)
        rendered_blocks = [self._render_block(block) for block in protected_blocks]
        prompt = "\n".join(rendered_blocks)
        if len(prompt) >= budget:
            return prompt

        for block in optional_blocks:
            rendered = self._render_block(block)
            candidate = "\n".join([prompt, rendered])
            if len(candidate) <= budget:
                prompt = candidate
                continue
            remaining = budget - len(prompt) - 1
            clipped = self._clip_block(block, remaining)
            if clipped:
                prompt = "\n".join([prompt, clipped])
            break
        return prompt

    def _render_block(self, block: PromptBlock) -> str:
        return f"\n[{block.name}]\n{block.content}"

    def _clip_block(self, block: PromptBlock, max_chars: int) -> str:
        prefix = f"\n[{block.name}]\n"
        marker = "\n- ... 已按 prompt budget 截断"
        available = max_chars - len(prefix) - len(marker)
        if available <= 0:
            return ""
        selected: list[str] = []
        used = 0
        for line in block.content.splitlines():
            next_used = used + len(line) + (1 if selected else 0)
            if next_used > available:
                if not selected and available > 12:
                    selected.append(line[:available].rstrip())
                break
            selected.append(line)
            used = next_used
        if not selected:
            return ""
        selected_text = "\n".join(selected)
        return f"{prefix}{selected_text}{marker}"

    def _memory_block(self, active_context: ActiveContext) -> str:
        if not active_context.memories:
            return "- 无活跃事件记忆"
        lines = []
        for memory in active_context.memories:
            lines.append(f"- [{memory.kind}] {memory.content}")
        return "\n".join(lines)

    def _semantic_block(self, semantics: list[SemanticMemory]) -> str:
        if not semantics:
            return "- 无活跃事实记忆"
        lines = []
        for item in semantics:
            lines.append(
                f"- {item.subject} {item.predicate} {item.object_value} "
                f"(confidence={item.confidence:.2f})"
            )
        return "\n".join(lines)

    def _relation_block(self, relations: list[RelationEdge]) -> str:
        if not relations:
            return "- 无活跃关系边"
        lines = []
        for edge in relations:
            lines.append(
                f"- {edge.source_id} -[{edge.relation_type}:{edge.weight:.2f}]-> "
                f"{edge.target_id}; confidence={edge.confidence:.2f}"
            )
        return "\n".join(lines)

    def _concept_block(self, nodes: list[ConceptNode]) -> str:
        if not nodes:
            return "- 无概念上下文"
        lines = []
        for node in nodes:
            snippet = node.memory_items[:120].replace("\n", " ")
            lines.append(f"- [{node.concept}] (w={node.weight:.1f}) {snippet}")
        return "\n".join(lines)

    def _person_info_block(self, info: dict[str, Any]) -> str:
        """Render structured person info as prompt context."""
        if not info:
            return "- 无用户详细信息"
        lines = []
        for key, value in info.items():
            if value and key != "user_id":
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) if lines else "- 无用户详细信息"
