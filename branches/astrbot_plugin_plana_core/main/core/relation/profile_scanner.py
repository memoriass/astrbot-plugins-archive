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
from ..storage import PlanaStorage

# Nickname extraction patterns
_NICKNAME_PATTERNS = [
    re.compile(
        r"(?:叫我|称呼我|我(?:的)?(?:名字|昵称)(?:是|叫))\s*(.{1,12})", re.IGNORECASE
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
    ) -> dict[str, Any]:
        uid = identity.global_user_id
        if not self.should_scan(uid):
            return {"skipped": True, "reason": "cooldown"}
        self._last_scan[uid] = time()

        profile_written = 0
        relation_written = 0
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
                profile_written += 1

        for item in items:
            evidence = f"profile_scanner:{item.kind}@{now_ts}"
            if item.kind == MEMORY_KIND_USER_PREFERENCE:
                self.storage.upsert_semantic(
                    scope_id,
                    f"user:{uid}",
                    item.predicate or "preference",
                    item.object_value or item.content,
                    item.confidence,
                    evidence,
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
                profile_written += 1
            elif item.kind == MEMORY_KIND_RELATIONSHIP_NOTE:
                self.storage.upsert_relation(
                    uid,
                    "plana:core",
                    "relationship_note",
                    max(item.importance, 0.4),
                    item.confidence,
                    evidence,
                )
                relation_written += 1
        return {
            "skipped": False,
            "profile_written": profile_written,
            "relation_written": relation_written,
            "nickname": nickname_found,
        }

    def _extract_nickname(self, text: str) -> str | None:
        """Try to extract a nickname from user message text."""
        for pattern in _NICKNAME_PATTERNS:
            m = pattern.search(text)
            if m:
                candidate = m.group(1).strip().rstrip("。.!！?？,，")
                if 1 <= len(candidate) <= 16:
                    return candidate
        return None
