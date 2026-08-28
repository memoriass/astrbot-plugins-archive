from __future__ import annotations

import re
from time import time
from typing import Any

from ..identity.models import UserIdentity
from ..memory.classifier import StructuredMemoryItem
from ..memory.models import (
    MEMORY_KIND_PROMISE,
    MEMORY_KIND_RELATIONSHIP_NOTE,
    MEMORY_KIND_USER_FACT,
    MEMORY_KIND_USER_PREFERENCE,
)
from ..plugin.storage import PlanaStorage

GLOBAL_PROFILE_SCOPE = "global"
GLOBAL_PROFILE_FACT_PREDICATES = {
    "birthday",
    "display_name",
    "language",
    "locale",
    "name",
    "nickname",
    "pronouns",
    "timezone",
}

# Nickname extraction patterns
_NICKNAME_PATTERNS = [
    re.compile(
        r"(?:叫我|称呼我|我的(?:名字|昵称)(?:是|叫)?)\s*(.{1,12})", re.IGNORECASE
    ),
    re.compile(
        r"(?:call me|my name is|i'm|i am)\s+([A-Za-z\u4e00-\u9fff]{1,16})",
        re.IGNORECASE,
    ),
]


class ProfileScanner:
    """Project structured memories into user profile semantics and relations.

    Enhanced with:
    - Nickname extraction from user messages
    - Evidence window (timestamped evidence tracking per semantic)
    - Per-user cooldown to avoid redundant scans within a short interval
    """

    # Minimum seconds between full scans for the same user
    DEFAULT_COOLDOWN = 30

    def __init__(self, storage: PlanaStorage, cooldown: int = DEFAULT_COOLDOWN):
        self.storage = storage
        self.cooldown = cooldown
        self._last_scan: dict[str, float] = {}
        self.evidence_store: Any | None = None

    def should_scan(self, user_id: str) -> bool:
        """Check if enough time has passed since last scan for this user."""
        last = self._last_scan.get(user_id, 0.0)
        return (time() - last) >= self.cooldown

    def apply(
        self,
        scope_id: str,
        identity: UserIdentity,
        items: list[StructuredMemoryItem],
        *,
        raw_text: str = "",
        source_memory_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        uid = identity.global_user_id
        if not self.should_scan(uid):
            return {"skipped": True, "reason": "cooldown"}
        self._last_scan[uid] = time()

        profile_written = 0
        relation_written = 0
        global_profile_written = 0
        nickname_found: str | None = None
        now_ts = int(time())

        # Nickname extraction from raw text
        if raw_text:
            nickname_found = self._extract_nickname(raw_text)
            if nickname_found:
                self.storage.upsert_semantic(
                    scope_id,
                    f"user:{uid}",
                    "nickname",
                    nickname_found,
                    0.85,
                    f"profile_scanner:nickname@{now_ts}",
                )
                self._record_evidence(
                    scope_id,
                    uid,
                    "nickname",
                    f"user:{uid}",
                    "nickname",
                    nickname_found,
                    0.85,
                    f"profile_scanner:nickname@{now_ts}",
                    0,
                )
                global_profile_written += self._mirror_global_profile(
                    scope_id=scope_id,
                    user_id=uid,
                    kind="nickname",
                    subject=f"user:{uid}",
                    predicate="nickname",
                    object_value=nickname_found,
                    confidence=0.85,
                    source=f"profile_scanner:global:nickname@{now_ts}",
                    source_memory_id=0,
                )
                profile_written += 1

        source_ids = source_memory_ids or []
        for index, item in enumerate(items):
            if not bool(getattr(item, "promotable", True)):
                continue
            evidence = f"profile_scanner:{item.kind}@{now_ts}"
            memory_id = source_ids[index] if index < len(source_ids) else 0
            if item.kind == MEMORY_KIND_USER_PREFERENCE:
                self.storage.upsert_semantic(
                    scope_id,
                    f"user:{uid}",
                    item.predicate or "preference",
                    item.object_value or item.content,
                    item.confidence,
                    evidence,
                )
                self._record_item_evidence(scope_id, uid, item, evidence, memory_id)
                global_profile_written += self._mirror_global_item(
                    scope_id, uid, item, evidence, memory_id
                )
                profile_written += 1
            elif item.kind == MEMORY_KIND_USER_FACT:
                self.storage.upsert_semantic(
                    scope_id,
                    f"user:{uid}",
                    item.predicate or "fact",
                    item.object_value or item.content,
                    item.confidence,
                    evidence,
                )
                self._record_item_evidence(scope_id, uid, item, evidence, memory_id)
                global_profile_written += self._mirror_global_item(
                    scope_id, uid, item, evidence, memory_id
                )
                profile_written += 1
            elif item.kind == MEMORY_KIND_PROMISE:
                self.storage.upsert_semantic(
                    scope_id,
                    f"user:{uid}",
                    item.predicate or "promise",
                    item.object_value or item.content,
                    item.confidence,
                    evidence,
                )
                self._record_item_evidence(scope_id, uid, item, evidence, memory_id)
                profile_written += 1
            elif item.kind == MEMORY_KIND_RELATIONSHIP_NOTE:
                self.storage.upsert_relation(
                    uid,
                    "plana:core",
                    "relationship_note",
                    max(item.importance, 0.4),
                    item.confidence,
                    evidence,
                    scope_id=scope_id,
                )
                self._record_item_evidence(scope_id, uid, item, evidence, memory_id)
                relation_written += 1
        return {
            "skipped": False,
            "profile_written": profile_written,
            "relation_written": relation_written,
            "global_profile_written": global_profile_written,
            "nickname": nickname_found,
        }

    def _extract_nickname(self, text: str) -> str | None:
        """Try to extract a nickname from user message text."""
        for pattern in _NICKNAME_PATTERNS:
            m = pattern.search(text)
            if m:
                candidate = m.group(1).strip().rstrip("。?!？！：:")
                if 1 <= len(candidate) <= 16:
                    return candidate
        return None

    def _record_item_evidence(
        self,
        scope_id: str,
        user_id: str,
        item: StructuredMemoryItem,
        source: str,
        source_memory_id: int,
    ) -> None:
        self._record_evidence(
            scope_id,
            user_id,
            item.kind,
            item.subject or f"user:{user_id}",
            item.predicate or item.kind,
            item.object_value or item.content,
            item.confidence,
            source,
            source_memory_id,
        )

    def _record_evidence(
        self,
        scope_id: str,
        user_id: str,
        kind: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
        source_memory_id: int,
    ) -> None:
        store = self.evidence_store
        if store is None:
            return
        store.record_evidence(
            scope_id=scope_id,
            user_id=user_id,
            kind=kind,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            confidence=confidence,
            source=source,
            source_memory_id=source_memory_id,
        )

    def _mirror_global_item(
        self,
        scope_id: str,
        user_id: str,
        item: StructuredMemoryItem,
        source: str,
        source_memory_id: int,
    ) -> int:
        if not self._should_mirror_global_item(item):
            return 0
        return self._mirror_global_profile(
            scope_id=scope_id,
            user_id=user_id,
            kind=item.kind,
            subject=item.subject or f"user:{user_id}",
            predicate=item.predicate or item.kind,
            object_value=item.object_value or item.content,
            confidence=item.confidence,
            source=f"{source}:global",
            source_memory_id=source_memory_id,
        )

    def _should_mirror_global_item(self, item: StructuredMemoryItem) -> bool:
        if item.kind == MEMORY_KIND_USER_PREFERENCE:
            return True
        if item.kind != MEMORY_KIND_USER_FACT:
            return False
        predicate = str(item.predicate or "").strip().lower()
        return predicate in GLOBAL_PROFILE_FACT_PREDICATES

    def _mirror_global_profile(
        self,
        *,
        scope_id: str,
        user_id: str,
        kind: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str,
        source_memory_id: int,
    ) -> int:
        if scope_id == GLOBAL_PROFILE_SCOPE or not object_value.strip():
            return 0
        self.storage.upsert_semantic(
            GLOBAL_PROFILE_SCOPE,
            subject,
            predicate,
            object_value,
            confidence,
            source,
        )
        self._record_evidence(
            GLOBAL_PROFILE_SCOPE,
            user_id,
            kind,
            subject,
            predicate,
            object_value,
            confidence,
            source,
            source_memory_id,
        )
        return 1
