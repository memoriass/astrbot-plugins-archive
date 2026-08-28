from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from time import time
from typing import Any


@dataclass(frozen=True, slots=True)
class DialogueLedgerEntry:
    timestamp: float
    scope_id: str
    unified_msg_origin: str
    role: str
    sender_id: str
    sender_name: str
    message_type: str
    text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": int(self.timestamp),
            "scope_id": self.scope_id,
            "unified_msg_origin": self.unified_msg_origin,
            "role": self.role,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "message_type": self.message_type,
            "text": self.text,
        }


class DialogueLedger:
    """Transient per-session conversation window.

    This is intentionally in-memory only. Long-lived memory still belongs to the
    memory kernel and confirmation-controlled workflow paths.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        capacity_per_session: int = 80,
        max_message_chars: int = 500,
    ) -> None:
        self.enabled = enabled
        self.capacity_per_session = max(1, min(int(capacity_per_session), 500))
        self.max_message_chars = max(80, min(int(max_message_chars), 3000))
        self._entries: dict[str, deque[DialogueLedgerEntry]] = {}
        self._processed_until: dict[str, float] = {}

    @classmethod
    def from_config(cls, config: Any) -> "DialogueLedger":
        return cls(
            enabled=bool(config.get("enable_dialogue_ledger", True)),
            capacity_per_session=_int_config(config, "dialogue_ledger_capacity", 80),
            max_message_chars=_int_config(
                config,
                "dialogue_ledger_max_message_chars",
                500,
            ),
        )

    def ingest_event(self, runtime: Any, event: Any) -> None:
        if not self.enabled:
            return
        text = self._event_text(event)
        if not text:
            return
        self._append(
            DialogueLedgerEntry(
                timestamp=time(),
                scope_id=self._scope_id(runtime, event),
                unified_msg_origin=self._origin(event),
                role="user",
                sender_id=str(event.get_sender_id() or ""),
                sender_name=self._sender_name(event),
                message_type=self._message_type(event),
                text=self._clean_text(text),
            )
        )

    def ingest_response(self, runtime: Any, event: Any, text: str) -> None:
        if not self.enabled:
            return
        clean = self._clean_text(text)
        if not clean:
            return
        timestamp = time()
        self._append(
            DialogueLedgerEntry(
                timestamp=timestamp,
                scope_id=self._scope_id(runtime, event),
                unified_msg_origin=self._origin(event),
                role="assistant",
                sender_id="plana",
                sender_name="Plana",
                message_type=self._message_type(event),
                text=clean,
            )
        )
        self.mark_processed(self._origin(event), timestamp=timestamp)

    def recent(
        self,
        unified_msg_origin: str,
        *,
        limit: int = 20,
        query: str = "",
        sender: str = "",
    ) -> list[dict[str, object]]:
        entries = list(self._entries.get(str(unified_msg_origin or ""), ()))
        if query:
            entries = self._filter_query(entries, query)
        if sender:
            entries = self._filter_sender(entries, sender)
        bounded = entries[-self._limit(limit) :]
        return [entry.to_dict() for entry in bounded]

    def prompt_block(
        self,
        unified_msg_origin: str,
        *,
        limit: int = 8,
        exclude_latest_text: str = "",
    ) -> str:
        key = str(unified_msg_origin or "")
        entries = self._prompt_entries(key, limit, exclude_latest_text)
        if not entries:
            return ""
        processed_until = self._processed_until.get(key, 0.0)
        handled = [entry for entry in entries if entry.timestamp <= processed_until]
        pending = [entry for entry in entries if entry.timestamp > processed_until]
        lines = [
            "[Current session dialogue ledger]",
            "Coverage: in-memory current session only; not long-term memory.",
        ]
        if handled:
            lines.append("[Handled context tail]")
            lines.extend(self._format_prompt_entry(entry) for entry in handled)
            lines.append("[/Handled context tail]")
        if pending:
            lines.append("[New messages since last handled turn]")
            lines.extend(self._format_prompt_entry(entry) for entry in pending)
            lines.append("[/New messages since last handled turn]")
        lines.append("[/Current session dialogue ledger]")
        return "\n".join(lines)

    def mark_processed(
        self,
        unified_msg_origin: str,
        *,
        timestamp: float | None = None,
    ) -> None:
        key = str(unified_msg_origin or "")
        if not key:
            return
        if timestamp is None:
            bucket = self._entries.get(key)
            if not bucket:
                return
            timestamp = bucket[-1].timestamp
        self._processed_until[key] = max(
            float(timestamp),
            self._processed_until.get(key, 0.0),
        )

    def coverage(self, unified_msg_origin: str) -> dict[str, object]:
        key = str(unified_msg_origin or "")
        entries = list(self._entries.get(key, ()))
        processed_until = self._processed_until.get(key, 0.0)
        unprocessed = sum(1 for entry in entries if entry.timestamp > processed_until)
        return {
            "coverage_status": "current_session_only",
            "storage": "in_memory_runtime_only",
            "total_count": len(entries),
            "unprocessed_count": unprocessed,
            "processed_until": int(processed_until) if processed_until else 0,
            "capacity": self.capacity_per_session,
        }

    def _append(self, entry: DialogueLedgerEntry) -> None:
        key = entry.unified_msg_origin
        if not key:
            return
        bucket = self._entries.setdefault(
            key,
            deque(maxlen=self.capacity_per_session),
        )
        if bucket and entry.timestamp <= bucket[-1].timestamp:
            entry = replace(entry, timestamp=bucket[-1].timestamp + 0.000001)
        bucket.append(entry)

    def _prompt_entries(
        self,
        unified_msg_origin: str,
        limit: int,
        exclude_latest_text: str,
    ) -> list[DialogueLedgerEntry]:
        entries = list(self._entries.get(unified_msg_origin, ()))
        if exclude_latest_text and entries:
            latest_text = entries[-1].text.strip()
            excluded = " ".join(exclude_latest_text.split())[: self.max_message_chars]
            if latest_text == excluded:
                entries = entries[:-1]
        return entries[-self._limit(limit) :]

    def _format_prompt_entry(self, entry: DialogueLedgerEntry) -> str:
        speaker = entry.sender_name or entry.sender_id or "user"
        timestamp = int(entry.timestamp)
        return f"- {entry.role}/{speaker} @{timestamp}: {entry.text}"

    def _filter_query(
        self,
        entries: list[DialogueLedgerEntry],
        query: str,
    ) -> list[DialogueLedgerEntry]:
        clean = " ".join(query.lower().split())
        if not clean:
            return entries
        terms = [term for term in clean.split() if len(term) >= 2]
        if not terms:
            terms = [clean]
        return [
            entry
            for entry in entries
            if any(term in entry.text.lower() for term in terms)
        ]

    def _filter_sender(
        self,
        entries: list[DialogueLedgerEntry],
        sender: str,
    ) -> list[DialogueLedgerEntry]:
        clean = sender.lower().strip()
        if not clean:
            return entries
        return [
            entry
            for entry in entries
            if clean in entry.sender_id.lower() or clean in entry.sender_name.lower()
        ]

    def _limit(self, value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 20
        return max(1, min(parsed, self.capacity_per_session))

    def _scope_id(self, runtime: Any, event: Any) -> str:
        origin = self._origin(event)
        resolver = getattr(runtime, "resolve_scope", None)
        if callable(resolver):
            try:
                return str(resolver(origin))
            except Exception:  # noqa: BLE001
                return origin
        return origin

    def _origin(self, event: Any) -> str:
        return str(getattr(event, "unified_msg_origin", "") or "global")

    def _event_text(self, event: Any) -> str:
        try:
            return str(event.get_message_str() or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _sender_name(self, event: Any) -> str:
        getter = getattr(event, "get_sender_name", None)
        if callable(getter):
            try:
                return str(getter() or event.get_sender_id() or "")
            except Exception:  # noqa: BLE001
                return str(event.get_sender_id() or "")
        return str(event.get_sender_id() or "")

    def _message_type(self, event: Any) -> str:
        try:
            message_type = event.get_message_type()
        except Exception:  # noqa: BLE001
            return ""
        return str(getattr(message_type, "value", message_type))

    def _clean_text(self, text: str) -> str:
        return " ".join(str(text or "").split())[: self.max_message_chars]


def _int_config(config: Any, key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default
