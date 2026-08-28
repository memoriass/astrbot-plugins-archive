from __future__ import annotations

import hashlib
import json
from datetime import datetime
from time import time
from typing import Any


class MemoryWarehousePusher:
    """Core-owned ingestion policy for the passive Memory Warehouse."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def push_message(
        self,
        event: Any,
        *,
        scope_id: str,
        actor_id: str,
        actor_name: str,
        content: str,
    ) -> dict[str, Any]:
        if not self._enabled("memory_warehouse_push_messages"):
            return {"ok": False, "skipped": "message_push_disabled"}
        return self._ingest_event(
            event,
            scope_id=scope_id,
            actor_id=actor_id,
            actor_name=actor_name,
            role="user",
            event_type="message",
            content=content,
            source="core_message_event",
        )

    def push_response(
        self,
        event: Any,
        *,
        scope_id: str,
        actor_id: str,
        actor_name: str,
        content: str,
    ) -> dict[str, Any]:
        if not self._enabled("memory_warehouse_push_llm_responses"):
            return {"ok": False, "skipped": "response_push_disabled"}
        return self._ingest_event(
            event,
            scope_id=scope_id,
            actor_id=actor_id,
            actor_name=actor_name,
            role="assistant",
            event_type="llm_response",
            content=content,
            source="core_llm_response",
        )

    def push_maintenance_summary(
        self,
        scope_id: str,
        *,
        consolidation_report: Any | None = None,
        decay_report: Any | None = None,
    ) -> dict[str, Any]:
        if not self._enabled("memory_warehouse_push_maintenance"):
            return {"ok": False, "skipped": "maintenance_push_disabled"}
        scope = str(scope_id or "global")[:200]
        today = datetime.now().strftime("%Y-%m-%d")
        memories = self._important_memories(scope, limit=8)
        lines = [
            f"Plana memory maintenance summary for {scope} on {today}.",
            self._report_line("consolidation", consolidation_report),
            self._report_line("decay", decay_report),
        ]
        if memories:
            lines.append("Important short-term Core memories retained locally:")
            for item in memories:
                lines.append(
                    "- "
                    f"{item.kind} importance={item.importance:.2f}: "
                    f"{self._clip(item.content, 220)}"
                )
        content = "\n".join(line for line in lines if line)
        client = self._client()
        if client is None:
            return {"ok": False, "skipped": "warehouse_client_unavailable"}
        return client.ingest(
            content=content,
            scope_id=scope,
            actor_id="plana:core",
            actor_name="Plana Core",
            role="system",
            event_type="daily_memory_maintenance",
            external_event_id=f"plana-core:{scope}:memory-maintenance:{today}",
            created_at=int(time()),
            metadata={
                "source": "core_memory_maintenance",
                "hippocampus_layer": "warehouse_long_term_archive",
                "core_policy_owner": True,
                "daily_window": today,
            },
        )

    def push_structured_memory(
        self,
        event: Any,
        *,
        scope_id: str,
        actor_id: str,
        actor_name: str,
        item: Any,
        source_memory_id: int,
    ) -> dict[str, Any]:
        if not self._enabled("memory_warehouse_push_structured_memories"):
            return {"ok": False, "skipped": "structured_push_disabled"}
        content = " ".join(str(getattr(item, "content", "") or "").split())
        if not content:
            return {"ok": False, "skipped": "empty_content"}
        return self._ingest_event(
            event,
            scope_id=scope_id,
            actor_id=actor_id,
            actor_name=actor_name,
            role="system",
            event_type="structured_memory_extract",
            content=content,
            source="core_structured_memory_extract",
            metadata={
                "memory_kind": str(getattr(item, "kind", "") or "")[:80],
                "subject": str(getattr(item, "subject", "") or "")[:200],
                "predicate": str(getattr(item, "predicate", "") or "")[:80],
                "object_value": str(getattr(item, "object_value", "") or "")[:800],
                "canonical_summary": str(
                    getattr(item, "canonical_summary", "") or ""
                )[:800],
                "persona_summary": str(getattr(item, "persona_summary", "") or "")[
                    :800
                ],
                "summary_quality": str(
                    getattr(item, "summary_quality", "normal") or "normal"
                )[:40],
                "summary_schema_version": str(
                    getattr(
                        item,
                        "summary_schema_version",
                        "plana-memory-summary-v1",
                    )
                    or "plana-memory-summary-v1"
                )[:80],
                "promotable_to_profile": bool(getattr(item, "promotable", True)),
                "confidence": float(getattr(item, "confidence", 0.0) or 0.0),
                "importance": float(getattr(item, "importance", 0.0) or 0.0),
                "source_memory_id": max(0, int(source_memory_id or 0)),
                "hippocampus_layer": "warehouse_core_structured_evidence",
            },
        )

    def push_profile_snapshot(
        self,
        *,
        scope_id: str,
        user_id: str,
        actor_name: str,
        snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self._enabled("memory_warehouse_push_profile_snapshots"):
            return {"ok": False, "skipped": "profile_snapshot_push_disabled"}
        snapshot_id = int((snapshot or {}).get("snapshot_id") or 0)
        if snapshot_id <= 0:
            return {"ok": False, "skipped": "snapshot_unavailable"}
        rows = self._profile_snapshots(scope_id, user_id)
        if not rows:
            return {"ok": False, "skipped": "snapshot_not_found"}
        row = rows[0]
        content = self._snapshot_content(row)
        client = self._client()
        if client is None:
            return {"ok": False, "skipped": "warehouse_client_unavailable"}
        return client.ingest(
            content=content,
            scope_id=scope_id,
            actor_id=user_id,
            actor_name=actor_name,
            role="system",
            event_type="profile_snapshot",
            external_event_id=f"plana-core:{scope_id}:profile:{user_id}:{snapshot_id}",
            created_at=int(row.get("created_at") or time()),
            metadata={
                "source": "core_profile_snapshot",
                "core_policy_owner": True,
                "snapshot_id": snapshot_id,
                "semantic_count": int(row.get("semantic_count") or 0),
                "relation_count": int(row.get("relation_count") or 0),
                "hippocampus_layer": "warehouse_core_profile_snapshot",
            },
        )

    def _ingest_event(
        self,
        event: Any,
        *,
        scope_id: str,
        actor_id: str,
        actor_name: str,
        role: str,
        event_type: str,
        content: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean = " ".join(str(content or "").split())
        if not clean:
            return {"ok": False, "skipped": "empty_content"}
        client = self._client()
        if client is None:
            return {"ok": False, "skipped": "warehouse_client_unavailable"}
        meta = {
            "source": source,
            "core_policy_owner": True,
            "hippocampus_layer": "warehouse_evidence_archive",
        }
        if isinstance(metadata, dict):
            meta.update(metadata)
            meta["source"] = source
            meta["core_policy_owner"] = True
        return client.ingest(
            content=clean,
            scope_id=scope_id,
            unified_msg_origin=str(getattr(event, "unified_msg_origin", "") or "")[:260],
            actor_id=actor_id,
            actor_name=actor_name,
            role=role,
            event_type=event_type,
            external_event_id=self._external_event_id(event, role, event_type, clean),
            platform=self._safe_call(event, "get_platform_name"),
            message_type=self._message_type(event),
            session_id=self._safe_call(event, "get_session_id"),
            group_id=self._safe_call(event, "get_group_id"),
            created_at=int(time()),
            metadata=meta,
        )

    def _client(self) -> Any | None:
        client = getattr(self.runtime, "memory_warehouse_client", None)
        if client is None or not getattr(client, "configured", False):
            return None
        return client

    def _enabled(self, attr: str) -> bool:
        return bool(getattr(self.runtime, attr, False))

    def _important_memories(self, scope_id: str, *, limit: int) -> list[Any]:
        try:
            memories = self.runtime.storage.recent_memories(scope_id, max(limit * 3, 12))
        except Exception:  # noqa: BLE001
            return []
        filtered = [
            item
            for item in memories
            if float(getattr(item, "importance", 0.0) or 0.0) >= 0.35
        ]
        return sorted(filtered, key=lambda item: item.importance, reverse=True)[:limit]

    def _profile_snapshots(self, scope_id: str, user_id: str) -> list[dict[str, Any]]:
        store = getattr(self.runtime, "profile_evidence_storage", None)
        if store is None:
            return []
        try:
            return store.recent_snapshots(scope_id, user_id, 1)
        except Exception:  # noqa: BLE001
            return []

    def _snapshot_content(self, row: dict[str, Any]) -> str:
        summary = " ".join(str(row.get("summary") or "").split())
        profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
        profile_text = json.dumps(profile, ensure_ascii=False, default=str)
        return "\n".join(
            line
            for line in [
                "Core profile snapshot.",
                f"Summary: {summary[:1200]}",
                f"Profile: {profile_text[:2500]}",
            ]
            if line
        )

    def _report_line(self, label: str, report: Any | None) -> str:
        if report is None:
            return f"{label}: skipped."
        parts = []
        for name in (
            "processed",
            "skipped",
            "semantic_written",
            "decayed",
            "archived",
            "atom_expired",
            "atom_forgotten",
        ):
            if hasattr(report, name):
                parts.append(f"{name}={getattr(report, name)}")
        return f"{label}: " + ", ".join(parts) + "."

    def _external_event_id(
        self,
        event: Any,
        role: str,
        event_type: str,
        content: str,
    ) -> str:
        platform = self._safe_call(event, "get_platform_name")
        origin = str(getattr(event, "unified_msg_origin", "") or "")
        message_id = self._message_id(event)
        if message_id:
            suffix = event_type
            if role == "assistant":
                suffix = f"{suffix}:{self._hash(content)[:12]}"
            return f"{platform}:{origin}:{message_id}:{suffix}"[:260]
        return f"plana-core:{origin}:{event_type}:{self._hash(content)[:24]}"[:260]

    def _message_id(self, event: Any) -> str:
        for path in (
            ("message_id",),
            ("message_obj", "message_id"),
            ("message_obj", "raw_message", "message_id"),
            ("message_obj", "raw_message", "message", "message_id"),
            ("message_obj", "raw_message", "message", "id"),
        ):
            value = self._nested_attr(event, path)
            if value not in {None, ""}:
                return str(value)[:160]
        return ""

    def _nested_attr(self, obj: Any, path: tuple[str, ...]) -> Any:
        value = obj
        for name in path:
            value = getattr(value, name, None)
            if value is None:
                return None
        return value

    def _message_type(self, event: Any) -> str:
        value = self._safe_call_raw(event, "get_message_type")
        return str(getattr(value, "value", value) or "")[:80]

    def _safe_call(self, event: Any, method_name: str) -> str:
        value = self._safe_call_raw(event, method_name)
        return "" if value is None else str(value)[:240]

    def _safe_call_raw(self, event: Any, method_name: str) -> Any:
        method = getattr(event, method_name, None)
        if not callable(method):
            return None
        try:
            return method()
        except Exception:  # noqa: BLE001
            return None

    def _hash(self, text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()

    def _clip(self, text: str, limit: int) -> str:
        clean = " ".join(str(text or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 3)].rstrip() + "..."
