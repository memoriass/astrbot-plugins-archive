from __future__ import annotations

import json
import random
import re

from astrbot.api.event import AstrMessageEvent

from ..memory import (
    MEMORY_KIND_RISK_EVENT,
    MEMORY_KIND_TOOL_RESULT,
)
from ..persona import EmotionVector, PlanaState
from .runtime_debug import build_debug_status_payload
from .runtime_labels import mode_label


class PlanaRuntimeOpsMixin:
    def record_tool_result(
        self,
        scope_id: str,
        user_id: str,
        tool_name: str,
        objective: str,
        result_summary: str,
        success: bool,
        risk_level: str = "normal",
        task_id: int = 0,
    ) -> dict[str, int]:
        if not self.enabled:
            return {"tool_written": 0, "episodic_written": 0, "semantic_written": 0}
        clean_result = " ".join(result_summary.replace("\n", " ").split())[:600]
        clean_objective = " ".join(objective.replace("\n", " ").split())[:600]
        self.storage.add_tool_memory(
            task_id,
            user_id,
            tool_name,
            clean_objective,
            clean_result,
            success,
            risk_level,
        )
        outcome = "succeeded" if success else "failed"
        content = f"Tool {tool_name} {outcome}: {clean_objective} -> {clean_result}"
        self.memory_kernel.ingest_text(
            scope_id,
            f"tool:{tool_name[:80]}",
            content,
            kind=MEMORY_KIND_TOOL_RESULT,
            importance=0.65 if success else 0.75,
            source="tool_result",
            semantic_predicate="last_result",
            semantic_value=clean_result or clean_objective,
            semantic_confidence=0.75,
        )
        if risk_level in {"medium", "high"}:
            self.memory_kernel.ingest_text(
                scope_id,
                user_id,
                f"Tool risk {risk_level}: {clean_objective}",
                kind=MEMORY_KIND_RISK_EVENT,
                importance=0.8,
                source="tool_result",
            )
            return {"tool_written": 1, "episodic_written": 2, "semantic_written": 1}
        return {"tool_written": 1, "episodic_written": 1, "semantic_written": 1}

    def recall_memory(
        self,
        scope_id: str = "global",
        query: str = "",
        kind: str = "",
        k: int | float | str | None = None,
    ) -> dict[str, object]:
        """Recall long-term memory with lightweight RRF fusion."""
        return self.memory_kernel.search(scope_id, query, kind, k)

    async def auto_accumulate_concepts(self, scope_id: str, provider) -> dict[str, int]:
        """Compress recent memories into concept graph entries."""
        if not self.enable_concept_extraction or provider is None:
            return {"processed": 0, "written": 0, "skipped": 0}
        try:
            return await self.memory_accumulator.accumulate(scope_id, provider)
        except Exception:  # noqa: BLE001
            return {"processed": 0, "written": 0, "skipped": 0}

    def set_mode(self, mode: str) -> bool:
        valid_modes = {
            "standby",
            "observing",
            "tasking",
            "checking",
            "risk_review",
            "waiting_confirm",
            "reporting",
            "handoff_to_bridge",
            "silent",
        }
        if mode not in valid_modes:
            return False
        state = self.storage.get_state("global", self.mode)
        self.storage.set_state(
            "global",
            PlanaState(
                mode=mode,
                mood_state=state.mood_state,
                emotion=state.emotion,
            ),
        )
        self.mode = mode
        return True

    def decay_state(self) -> None:
        """Gently decay the persisted emotion vector toward baseline."""
        state = self.storage.get_state("global", self.mode)
        self.storage.set_state(
            "global",
            PlanaState(
                mode=state.mode,
                mood_state=state.mood_state,
                emotion=state.emotion.decay_toward_baseline(),
            ),
        )

    async def update_mood_by_response(self, text: str, provider) -> None:
        """Probabilistically update mood_state using LLM."""
        if self.mood_update_probability <= 0.0:
            return
        if random.random() > self.mood_update_probability:
            return
        if provider is None:
            return
        state = self.storage.get_state("global", self.mode)
        persona_hint = self.persona_style.strip() or "沿用 AstrBot 当前会话人格"
        prompt = (
            f"你当前的情绪状态是：{state.mood_state}\n"
            f"你刚刚回复了用户以下内容（节选）：{text[:300]}\n"
            f"你的人格特点是：{persona_hint}\n"
            "返回严格 JSON："
            '{"mood_state":"不超过30字的中文状态","valence":0.0,'
            '"arousal":0.0,"dominance":0.0}。'
            "三个数值范围均为 -1 到 1，不要输出其他内容。"
        )
        try:
            response = await provider.text_chat(
                prompt=prompt,
                system_prompt=(
                    "你是一个内部情绪状态生成模块。"
                    "只返回包含 mood_state、valence、arousal、dominance 的 JSON。"
                ),
            )
            raw = str(getattr(response, "completion_text", "") or "").strip().strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
            payload = json.loads(raw)
            if isinstance(payload, dict) and str(payload.get("mood_state") or "").strip():
                emotion = EmotionVector(
                    valence=float(payload.get("valence", state.emotion.valence)),
                    arousal=float(payload.get("arousal", state.emotion.arousal)),
                    dominance=float(payload.get("dominance", state.emotion.dominance)),
                ).normalized()
                self.storage.set_state(
                    "global",
                    PlanaState(
                        mode=state.mode,
                        mood_state=str(payload.get("mood_state") or "").strip()[:120],
                        emotion=emotion,
                    ),
                )
        except Exception:  # noqa: BLE001
            pass

    def status_text(self) -> str:
        state = self.storage.get_state("global", self.mode)
        bridge_state = "enabled" if self.bridge_contract.enabled else "disabled"
        gallery_state = "enabled" if self.gallery_client.configured else "disabled"
        warehouse_state = self.memory_warehouse_client.state_label()
        return (
            "Plana Core\n"
            f"enabled={self.enabled}\n"
            f"mode={state.mode}\n"
            f"memory_activation={self.enable_memory_activation}\n"
            f"memory_consolidation={self.enable_memory_consolidation}\n"
            f"memory_decay={self.enable_memory_decay}\n"
            f"prompt_budget={self.max_prompt_chars}\n"
            f"relation_graph={self.enable_relation_graph}\n"
            f"recall_tool={self.enable_recall_tool}\n"
            f"bridge_api={bridge_state}\n"
            f"gallery_chat_images={gallery_state}\n"
            f"memory_warehouse={warehouse_state}"
        )

    def user_status_text(self) -> str:
        state = self.storage.get_state("global", self.mode)
        available = ["聊天"]
        if self.enable_recall_tool: available.append("记忆检索")
        if bool(self.config.get("assistant_remote_runner_enabled", False)):
            available.append("受控 Codex 委派")
        if self.bridge_contract.enabled: available.append("Bridge 入口")
        if self.gallery_client.configured: available.append("本地语境图片")
        if self.memory_warehouse_client.state_label() == "enabled": available.append("Memory Warehouse")
        return (
            "我在线，当前处于"
            f"{mode_label(state.mode)}模式。"
            f"可用能力：{'、'.join(available)}。"
            "需要内部诊断时请使用 /plana status。"
        )

    def search_text(self, event: AstrMessageEvent, query: str) -> str:
        result = self.memory_kernel.search(
            event.unified_msg_origin,
            query,
            "",
            self.max_active_memories,
        )
        lines = [f"Plana memory search: {query or '<recent>'}"]
        if result["memories"]:
            lines.append("episodic:")
            lines.extend(
                f"{item.id}. [{item.kind}] {item.content}"
                for item in result["memories"]
            )
        if result["semantics"]:
            lines.append("semantic:")
            lines.extend(
                f"{item.id}. {item.subject} {item.predicate} {item.object_value}"
                for item in result["semantics"]
            )
        if len(lines) == 1:
            return "Plana memory search: empty"
        return "\n".join(lines)

    def remember_text(self, event: AstrMessageEvent, content: str) -> str:
        text = content.strip()
        if not text:
            return "Plana remember: empty"
        identity = self.identity_from_event(event)
        self.memory_kernel.ingest_text(
            event.unified_msg_origin,
            identity.global_user_id,
            f"{identity.nickname}: {text}",
            kind="semantic_note",
            importance=0.45,
            source="plana_command",
            semantic_predicate="note",
            semantic_value=text,
            semantic_confidence=0.72,
        )
        return "Plana remember: stored"

    def graph_text(self, event: AstrMessageEvent, command: str = "") -> str:
        identity = self.identity_from_event(event)
        scope_id = self.resolve_scope(event.unified_msg_origin)
        if command.strip().lower() == "detail":
            return self.relation_graph.graph_detail_text(identity, self.graph_detail_limit, scope_id)
        return self.relation_graph.graph_text(identity, self.max_active_relations, scope_id)

    def debug_status_payload(self) -> dict[str, object]:
        return build_debug_status_payload(self)

    def consolidate_text(self, event: AstrMessageEvent) -> str:
        if not self.enabled or not self.enable_memory_consolidation:
            return "Plana consolidation: disabled"
        identity = self.identity_from_event(event)
        report = self.memory_consolidator.consolidate_scope(
            self.resolve_scope(event.unified_msg_origin),
            identity,
        )
        return (
            "Plana consolidation:\n"
            f"scope={report.scope_id}\n"
            f"processed={report.processed}\n"
            f"skipped={report.skipped}\n"
            f"semantic_written={report.semantic_written}"
        )

    def _sanitize_task_text(self, text: str) -> str:
        sanitized = re.sub(
            r"(?i)(token|password|credential|secret|key)=\S+",
            r"\1=<redacted>",
            text,
        )
        sanitized = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
            r"\1<redacted>",
            sanitized,
        )
        sanitized = re.sub(r"([A-Za-z]:\\[^ \t]+|/[^\s]+)", "<path>", sanitized)
        return sanitized[:600]
