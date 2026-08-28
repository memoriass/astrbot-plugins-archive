from __future__ import annotations

from typing import TYPE_CHECKING

from ..storage import PlanaStorage
from .models import ConsolidationReport, MemoryRecord

if TYPE_CHECKING:
    from ..identity.models import UserIdentity


class MemoryConsolidator:
    def __init__(self, storage: PlanaStorage, batch_size: int):
        self.storage = storage
        self.batch_size = max(1, batch_size)

    def consolidate_scope(
        self, scope_id: str, identity: UserIdentity
    ) -> ConsolidationReport:
        memories = self.storage.recent_memories(scope_id, self.batch_size * 2)
        report = ConsolidationReport(scope_id=scope_id)
        for memory in memories:
            if report.processed >= self.batch_size:
                break
            if self.storage.memory_has_link(memory.id, "consolidation"):
                report.skipped += 1
                continue
            semantic_count = self._extract_semantics(scope_id, identity, memory)
            self.storage.link_memory(
                memory.id,
                "consolidation",
                f"scope:{scope_id}",
                0.60 if semantic_count else 0.35,
            )
            report.processed += 1
            report.semantic_written += semantic_count
        return report

    def _extract_semantics(
        self,
        scope_id: str,
        identity: UserIdentity,
        memory: MemoryRecord,
    ) -> int:
        text = self._clean(memory.content)
        if not text:
            return 0
        written = 0
        profile_note = self._profile_note(text)
        if profile_note:
            self.storage.upsert_semantic(
                scope_id,
                identity.global_user_id,
                "profile_note",
                profile_note,
                0.68,
                "memory_consolidator",
            )
            written += 1
        task_note = self._task_note(text)
        if task_note:
            self.storage.upsert_semantic(
                scope_id,
                f"task:{scope_id}",
                "observed_need",
                task_note,
                0.62,
                "memory_consolidator",
            )
            written += 1
        if memory.importance >= 0.45 and not profile_note and not task_note:
            self.storage.upsert_semantic(
                scope_id,
                f"session:{scope_id}",
                "important_event",
                text[:360],
                min(max(memory.importance, 0.45), 0.80),
                "memory_consolidator",
            )
            written += 1
        return written

    def _profile_note(self, text: str) -> str:
        markers = ("我是", "我叫", "我的名字", "my name is", "i am ")
        lowered = text.lower()
        for marker in markers:
            index = lowered.find(marker.lower())
            if index >= 0:
                return text[index : index + 240].strip(" ：:，,。 ")
        return ""

    def _task_note(self, text: str) -> str:
        keywords = (
            "工具",
            "执行",
            "检查",
            "修复",
            "配置",
            "部署",
            "安装",
            "重启",
            "删除",
            "备份",
            "内网",
            "服务器",
            "数据库",
        )
        if any(keyword in text for keyword in keywords):
            return text[:360]
        return ""

    def _clean(self, text: str) -> str:
        return " ".join(text.replace("\n", " ").split())[:600]
