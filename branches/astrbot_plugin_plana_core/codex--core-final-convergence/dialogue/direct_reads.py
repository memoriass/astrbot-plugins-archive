from __future__ import annotations

import asyncio
import re
from typing import Any


class DialogueDirectReads:
    """Inline read-only replies for common chat UI natural-language queries."""

    async def reply_for(self, runtime: Any, event: Any, text: str, intent: str) -> str:
        if intent == "memory_query":
            return await self._memory_query(runtime, event, text)
        if intent == "profile_query":
            return self._profile_query(runtime, event)
        if intent == "context_preview":
            return self._context_preview(runtime, event, text)
        if intent == "conversation_history":
            return self._conversation_history(runtime, event, text)
        return ""

    async def _memory_query(self, runtime: Any, event: Any, text: str) -> str:
        query = self._query_text(
            text,
            (
                "search memory",
                "memory search",
                "recall",
                "查记忆",
                "搜索记忆",
                "检索记忆",
                "回忆一下",
                "回忆下",
                "我之前说过",
                "之前提到",
                "还记得",
                "记忆里",
            ),
        )
        kernel = getattr(runtime, "memory_kernel", None)
        if kernel is None or not hasattr(kernel, "search"):
            fallback = getattr(runtime, "search_text", None)
            if callable(fallback):
                return str(fallback(event, query))
            return "当前记忆检索不可用。"
        result = kernel.search(
            self._scope(runtime, event),
            query,
            "",
            getattr(runtime, "max_active_memories", 5),
        )
        lines = [f"记忆检索（只读）：{query or '最近记忆'}"]
        fused = list(result.get("results") or [])
        if fused:
            lines.append("命中结果：")
            for item in fused[:5]:
                title = self._value(item, "title") or self._value(item, "id")
                content = self._clip(self._value(item, "content"), 180)
                lines.append(f"- {title}: {content}")
            return "\n".join(lines)

        memories = list(result.get("memories") or [])
        semantics = list(result.get("semantics") or [])
        warehouse_lines = (
            await self._warehouse_memory_lines(runtime, event, text, query)
            if self._explicit_warehouse_intent(text) or not memories and not semantics
            else []
        )
        if memories:
            lines.append("事件记忆：")
            for item in memories[:5]:
                lines.append(
                    f"- #{self._value(item, 'id')} "
                    f"[{self._value(item, 'kind')}] "
                    f"{self._clip(self._value(item, 'content'), 180)}"
                )
        if semantics:
            lines.append("用户理解：")
            for item in semantics[:5]:
                subject = self._value(item, "subject")
                predicate = self._value(item, "predicate")
                value = self._clip(self._value(item, "object_value"), 160)
                lines.append(f"- {subject} {predicate}: {value}")
        if warehouse_lines:
            lines.extend(warehouse_lines)
        if len(lines) == 1:
            lines.append("没有找到匹配的长期记忆。")
        return "\n".join(lines)

    def _profile_query(self, runtime: Any, event: Any) -> str:
        kernel = getattr(runtime, "memory_kernel", None)
        if kernel is None or not hasattr(kernel, "get_person_profile"):
            return "当前用户理解不可用。"
        identity = self._identity(runtime, event)
        user_id = str(self._value(identity, "global_user_id") or "")
        profile = kernel.get_person_profile(self._scope(runtime, event), user_id, 12)
        summary = str(profile.get("person_summary") or "").strip()
        stats = profile.get("summary") or {}
        lines = ["用户理解（只读）："]
        lines.append(f"概要：{summary or '还没有形成稳定画像。'}")
        lines.append(
            "统计："
            f"语义条目={stats.get('semantic_items', 0)}，"
            f"偏好={stats.get('preferences', 0)}，"
            f"承诺={stats.get('promises', 0)}，"
            f"关系={stats.get('relationship_edges', 0)}"
        )
        semantics = list(profile.get("semantics") or [])
        if semantics:
            lines.append("主要条目：")
            for item in semantics[:5]:
                subject = self._value(item, "subject")
                predicate = self._value(item, "predicate")
                value = self._clip(self._value(item, "object_value"), 160)
                lines.append(f"- {subject} {predicate}: {value}")
        return "\n".join(lines)

    def _context_preview(self, runtime: Any, event: Any, text: str) -> str:
        query = self._query_text(
            text,
            (
                "context preview",
                "prompt context",
                "上下文预览",
                "提示词上下文",
                "注入上下文",
                "当前上下文",
            ),
        )
        try:
            from ..web.inspectors import build_context_preview_payload
        except Exception:  # noqa: BLE001
            return "当前上下文预览不可用。"
        payload = build_context_preview_payload(
            runtime,
            self._scope(runtime, event),
            query,
            "",
            5,
        )
        selected = payload.get("selected") or {}
        lines = ["上下文预览（只读）："]
        lines.extend(str(item) for item in payload.get("preview_lines") or [])
        lines.append(
            "融合结果="
            f"{len(selected.get('fused_results') or [])}，"
            f"召回缺口={selected.get('recall_gaps') or {}}"
        )
        return "\n".join(lines)

    def _conversation_history(self, runtime: Any, event: Any, text: str) -> str:
        ledger = getattr(runtime, "dialogue_ledger", None)
        if ledger is None:
            return "当前短期聊天记录不可用。"
        query = self._query_text(
            text,
            (
                "chat history",
                "conversation history",
                "recent messages",
                "recent chat",
                "summarize above",
                "summarize recent",
                "聊天记录",
                "群聊记录",
                "最近说",
                "刚才",
                "刚刚说",
                "上面",
                "前面",
                "谁说",
            ),
        )
        origin = str(getattr(event, "unified_msg_origin", "") or "global")
        messages = ledger.recent(origin, limit=8, query=query)
        query_matched = True
        if query and not messages:
            messages = ledger.recent(origin, limit=8)
            query_matched = False
        if not messages:
            return "当前会话还没有可用的短期聊天记录。"
        coverage = ledger.coverage(origin)
        lines = ["短期聊天记录（当前进程内，只读）："]
        if query and not query_matched:
            lines.append(f"未命中关键词“{query}”，以下为最近消息：")
        for item in messages[-8:]:
            speaker = item.get("sender_name") or item.get("sender_id") or item.get("role")
            role = item.get("role") or "user"
            lines.append(f"- {role}/{speaker}: {self._clip(item.get('text'), 180)}")
        lines.append(
            "覆盖："
            f"{coverage.get('coverage_status')}，"
            f"总数={coverage.get('total_count', 0)}，"
            f"未处理={coverage.get('unprocessed_count', 0)}"
        )
        return "\n".join(lines)

    def _workflow_status(self, text: str) -> str:
        lowered = str(text or "").lower()
        if any(token in lowered for token in ("all", "全部", "所有", "任意")):
            return "all"
        if any(token in lowered for token in ("completed", "done", "已完成", "完成")):
            return "completed"
        if any(token in lowered for token in ("cancelled", "canceled", "取消")):
            return "cancelled"
        if any(token in lowered for token in ("waiting_confirm", "待确认", "pending")):
            return "waiting_confirm"
        return "waiting_confirm"

    def _query_text(self, text: str, markers: tuple[str, ...]) -> str:
        clean = " ".join(str(text or "").strip().split())
        clean = re.sub(
            r"^(plana|普拉娜|普拉纳)[，,。！!\s]*",
            "",
            clean,
            flags=re.IGNORECASE,
        )
        lowered = clean.lower()
        for marker in markers:
            index = lowered.find(marker.lower())
            if index >= 0:
                clean = clean[index + len(marker) :]
                break
        clean = clean.strip(" ：:，,。 ")
        clean = re.sub(r"^(里)?(关于|一下|下|：|:|的)?", "", clean).strip(" ：:，,。 ")
        for phrase in (
            "只读查询",
            "只读方式",
            "只读",
            "不要写入",
            "不要修改任何数据",
            "不要修改数据",
            "不要修改",
            "不要确认或执行",
            "不要执行",
            "无需执行",
        ):
            clean = clean.replace(phrase, "")
        clean = clean.strip(" ：:，,。 ")
        clean = re.sub(r"(的内容|内容)$", "", clean).strip(" ：:，,。 ")
        return clean[:300]

    def _scope(self, runtime: Any, event: Any) -> str:
        origin = str(getattr(event, "unified_msg_origin", "") or "global")
        resolver = getattr(runtime, "resolve_scope", None)
        if callable(resolver):
            try:
                return str(resolver(origin))
            except Exception:  # noqa: BLE001
                return origin
        return origin

    def _identity(self, runtime: Any, event: Any) -> Any:
        getter = getattr(runtime, "identity_from_event", None)
        if callable(getter):
            try:
                return getter(event)
            except Exception:  # noqa: BLE001
                pass
        try:
            sender_id = str(event.get_sender_id() or "")
        except Exception:  # noqa: BLE001
            return {"global_user_id": ""}
        platform = self._event_platform(event)
        return {
            "global_user_id": f"{platform}:{sender_id}" if platform and sender_id else sender_id
        }

    async def _warehouse_memory_lines(
        self,
        runtime: Any,
        event: Any,
        text: str,
        query: str,
    ) -> list[str]:
        client = getattr(runtime, "memory_warehouse_client", None)
        if client is None or not bool(getattr(client, "enabled", False)):
            return []
        explicit = self._explicit_warehouse_intent(text)
        cross_scope = explicit and self._explicit_cross_scope_intent(text)
        if cross_scope and not self._is_private(event):
            cross_scope = False
        try:
            result = await asyncio.to_thread(
                client.search,
                query=query,
                scope_id="" if cross_scope else self._scope(runtime, event),
                unified_msg_origin="",
                actor_id=self._global_user_id(runtime, event) if cross_scope else "",
                limit=5,
            )
        except Exception:  # noqa: BLE001
            return ["Warehouse evidence: unavailable"] if explicit else []
        if not isinstance(result, dict):
            return []
        if result.get("ok") is False:
            return ["Warehouse evidence: unavailable"] if explicit else []
        rows = list(result.get("results") or [])
        if not rows:
            return []
        lines = ["Warehouse evidence (read-only, Core policy required):"]
        for item in rows[:5]:
            evidence_id = self._value(item, "evidence_id") or self._value(item, "id")
            snippet = self._clip(
                self._value(item, "snippet") or self._value(item, "content"),
                180,
            )
            lines.append(f"- {evidence_id}: {snippet}")
        return lines

    def _global_user_id(self, runtime: Any, event: Any) -> str:
        identity = self._identity(runtime, event)
        return str(self._value(identity, "global_user_id") or "")

    def _explicit_warehouse_intent(self, text: str) -> bool:
        lowered = str(text or "").lower()
        tokens = (
            "warehouse",
            "archive",
            "evidence",
            "long-term",
            "long term",
            "cross group",
            "cross-scope",
            "other group",
            "other groups",
            "memory warehouse",
            "仓库",
            "归档",
            "证据",
            "长期",
            "跨群",
            "其他群",
            "别的群",
            "以前群里",
        )
        return any(token in lowered for token in tokens)

    def _explicit_cross_scope_intent(self, text: str) -> bool:
        lowered = str(text or "").lower()
        tokens = (
            "cross group",
            "cross-scope",
            "other group",
            "other groups",
            "all groups",
            "跨群",
            "其他群",
            "别的群",
            "所有群",
            "以前群里",
        )
        return any(token in lowered for token in tokens)

    def _is_private(self, event: Any) -> bool:
        method = getattr(event, "is_private_chat", None)
        if callable(method):
            try:
                return bool(method())
            except Exception:  # noqa: BLE001
                return False
        return False

    def _event_platform(self, event: Any) -> str:
        method = getattr(event, "get_platform_name", None)
        if not callable(method):
            return ""
        try:
            return str(method() or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _value(self, item: Any, name: str) -> str:
        if isinstance(item, dict):
            return str(item.get(name, "") or "")
        return str(getattr(item, name, "") or "")

    def _clip(self, value: Any, limit: int = 180) -> str:
        clean = " ".join(str(value or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 3)].rstrip() + "..."
