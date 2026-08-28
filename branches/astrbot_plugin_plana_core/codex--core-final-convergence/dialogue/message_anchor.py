from __future__ import annotations

from dataclasses import dataclass
import json
from time import time
from typing import Any

from .delivery import reply_message_id_from_event


DEFAULT_MESSAGE_ANCHOR_TTL_SECONDS = 7 * 24 * 60 * 60
_PUBLIC_SCALAR_KEYS = frozenset(
    {
        "anchor_kind", "capability", "has_task", "media_intent",
        "requires_owner_confirmation", "result_type", "risk_class",
        "route", "status", "kind", "count", "season", "bgm_id",
    }
)
_PUBLIC_ITEM_KEYS = frozenset(
    {
        "id", "bgm_id", "title", "name", "subgroup", "release_date",
        "last_download_time", "type", "enable", "season", "current_episode",
        "total_episode", "update_day", "status", "item_count", "recent_titles",
    }
)


@dataclass(frozen=True, slots=True)
class MessageAnchor:
    scope_id: str
    message_id: str
    owner_actor_id: str
    task_id: str
    root_message_id: str
    source_message_id: str
    anchor_kind: str
    public_projection: dict[str, Any]
    created_at: int
    updated_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class MessageAnchorResolution:
    scope_id: str
    message_id: str
    owner_actor_id: str
    task_id: str
    root_message_id: str
    source_message_id: str
    anchor_kind: str
    public_projection: dict[str, Any]
    is_owner: bool
    can_inherit_task: bool
    can_confirm: bool
    created_at: int
    updated_at: int
    expires_at: int


class MessageAnchorStore:
    def __init__(self, database: Any) -> None:
        self.database = database

    def initialize(self) -> None:
        with self.database.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assistant_message_anchors (
                    scope_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    owner_actor_id TEXT NOT NULL,
                    task_id TEXT NOT NULL DEFAULT '',
                    root_message_id TEXT NOT NULL DEFAULT '',
                    source_message_id TEXT NOT NULL DEFAULT '',
                    anchor_kind TEXT NOT NULL DEFAULT 'assistant_message',
                    public_projection TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(scope_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_assistant_message_anchors_expiry
                ON assistant_message_anchors(expires_at);
                """
            )

    def register(self, anchor: MessageAnchor) -> None:
        projection = json.dumps(
            sanitize_public_projection(anchor.public_projection),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self.database.connect() as conn:
            conn.execute(
                "DELETE FROM assistant_message_anchors WHERE expires_at <= ?",
                (anchor.updated_at,),
            )
            conn.execute(
                """
                INSERT INTO assistant_message_anchors (
                    scope_id, message_id, owner_actor_id, task_id,
                    root_message_id, source_message_id, anchor_kind,
                    public_projection, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, message_id) DO UPDATE SET
                    owner_actor_id=excluded.owner_actor_id,
                    task_id=excluded.task_id,
                    root_message_id=excluded.root_message_id,
                    source_message_id=excluded.source_message_id,
                    anchor_kind=excluded.anchor_kind,
                    public_projection=excluded.public_projection,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (
                    _identifier(anchor.scope_id, "global"),
                    _identifier(anchor.message_id),
                    _identifier(anchor.owner_actor_id, "user"),
                    _identifier(anchor.task_id),
                    _identifier(anchor.root_message_id),
                    _identifier(anchor.source_message_id),
                    _identifier(anchor.anchor_kind, "assistant_message"),
                    projection,
                    anchor.created_at,
                    anchor.updated_at,
                    anchor.expires_at,
                ),
            )

    def resolve_reply(
        self,
        scope_id: str,
        reply_message_id: str,
        actor_id: str,
        *,
        now: int | None = None,
    ) -> MessageAnchorResolution | None:
        scope = _identifier(scope_id, "global")
        message_id = _identifier(reply_message_id)
        if not message_id:
            return None
        current = int(time()) if now is None else int(now)
        with self.database.connect() as conn:
            conn.execute(
                """
                DELETE FROM assistant_message_anchors
                WHERE scope_id=? AND message_id=? AND expires_at <= ?
                """,
                (scope, message_id, current),
            )
            row = conn.execute(
                """
                SELECT scope_id, message_id, owner_actor_id, task_id,
                       root_message_id, source_message_id, anchor_kind,
                       public_projection, created_at, updated_at, expires_at
                FROM assistant_message_anchors
                WHERE scope_id=? AND message_id=?
                LIMIT 1
                """,
                (scope, message_id),
            ).fetchone()
        if row is None:
            return None
        owner_actor_id = str(row["owner_actor_id"] or "")
        is_owner = bool(actor_id) and _identifier(actor_id) == owner_actor_id
        task_id = str(row["task_id"] or "") if is_owner else ""
        anchor_kind = str(row["anchor_kind"] or "assistant_message")
        return MessageAnchorResolution(
            scope_id=str(row["scope_id"] or ""),
            message_id=str(row["message_id"] or ""),
            owner_actor_id=owner_actor_id if is_owner else "",
            task_id=task_id,
            root_message_id=str(row["root_message_id"] or "") if is_owner else "",
            source_message_id=str(row["source_message_id"] or "") if is_owner else "",
            anchor_kind=anchor_kind,
            public_projection=_decode_public_projection(row["public_projection"]),
            is_owner=is_owner,
            can_inherit_task=is_owner and bool(task_id),
            can_confirm=is_owner and bool(task_id) and anchor_kind == "pending_confirmation",
            created_at=int(row["created_at"] or 0),
            updated_at=int(row["updated_at"] or 0),
            expires_at=int(row["expires_at"] or 0),
        )


def register_sent_message_anchors(
    event: Any,
    *,
    runtime: Any,
    store: MessageAnchorStore,
    session_store: Any | None = None,
    ttl_seconds: int = DEFAULT_MESSAGE_ANCHOR_TTL_SECONDS,
    now: int | None = None,
) -> int:
    if not bool(getattr(event, "_plana_anchor_outbound", False)):
        return 0
    message_ids = sent_message_ids_from_event(event)
    if not message_ids:
        return 0
    scope_id, actor_id = _conversation_identity(runtime, event)
    source_message_id = _source_message_id(event)
    state = _matching_session_state(session_store, scope_id, actor_id, event)
    task_id = _task_id_from_event(event, state)
    anchor_kind = _anchor_kind_from_event(event, state, task_id)
    projection = _public_projection_from_event(event, anchor_kind, task_id)
    inherited = store.resolve_reply(
        scope_id,
        reply_message_id_from_event(event),
        actor_id,
        now=now,
    )
    root_message_id = source_message_id
    if inherited is not None and inherited.is_owner:
        root_message_id = inherited.root_message_id
        if not task_id:
            task_id = inherited.task_id
            projection["has_task"] = bool(task_id)
    timestamp = int(time()) if now is None else int(now)
    ttl = max(60, min(int(ttl_seconds or DEFAULT_MESSAGE_ANCHOR_TTL_SECONDS), 7776000))
    root_message_id = root_message_id or source_message_id or message_ids[0]
    for message_id in message_ids:
        store.register(
            MessageAnchor(
                scope_id=scope_id,
                message_id=message_id,
                owner_actor_id=actor_id,
                task_id=task_id,
                root_message_id=root_message_id,
                source_message_id=source_message_id,
                anchor_kind=anchor_kind,
                public_projection=projection,
                created_at=timestamp,
                updated_at=timestamp,
                expires_at=timestamp + ttl,
            )
        )
    return len(message_ids)


def sent_message_ids_from_event(event: Any) -> list[str]:
    getter = getattr(event, "get_sent_message_ids", None)
    if not callable(getter):
        return []
    try:
        raw_ids = getter()
    except Exception:  # noqa: BLE001
        return []
    values: list[str] = []
    _collect_message_ids(raw_ids, values)
    return list(dict.fromkeys(values))


def sanitize_public_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    clean: dict[str, Any] = {}
    for key in _PUBLIC_SCALAR_KEYS:
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, str):
            text = _safe_public_text(item, 160)
            if text:
                clean[key] = text
    item = _sanitize_public_item(value.get("item"))
    if item:
        clean["item"] = item
    items = value.get("items")
    if isinstance(items, list):
        projected = [
            safe
            for safe in (_sanitize_public_item(source) for source in items[:8])
            if safe
        ]
        if projected:
            clean["items"] = projected
    return clean


def _sanitize_public_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    clean: dict[str, Any] = {}
    for key in _PUBLIC_ITEM_KEYS:
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, str):
            text = _safe_public_text(item, 240)
            if text:
                clean[key] = text
        elif key == "recent_titles" and isinstance(item, list):
            titles = [
                text
                for text in (_safe_public_text(title, 240) for title in item[:4])
                if text
            ]
            if titles:
                clean[key] = titles
    return clean


def _safe_public_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    lowered = text.casefold()
    if (
        not text
        or "://" in lowered
        or lowered.startswith(("www.", "magnet:", "/", "./", "../", "\\\\"))
        or "bearer " in lowered
        or any(
            marker in lowered
            for marker in ("token=", "api_key=", "apikey=", "password=")
        )
    ):
        return ""
    return text[:limit]


def _collect_message_ids(value: Any, output: list[str]) -> None:
    if isinstance(value, dict):
        for key in ("message_id", "messageId", "id"):
            if key in value:
                _collect_message_ids(value[key], output)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_message_ids(item, output)
        return
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        message_id = _identifier(value)
        if message_id:
            output.append(message_id)
        return
    message_id = _identifier(getattr(value, "message_id", ""))
    if message_id:
        output.append(message_id)


def _conversation_identity(runtime: Any, event: Any) -> tuple[str, str]:
    try:
        scope_id = str(runtime.resolve_scope(event.unified_msg_origin) or "global")
    except Exception:  # noqa: BLE001
        scope_id = str(getattr(event, "unified_msg_origin", "") or "global")
    try:
        actor_id = str(runtime.identity_from_event(event).global_user_id or "user")
    except Exception:  # noqa: BLE001
        getter = getattr(event, "get_sender_id", None)
        actor_id = str(getter() if callable(getter) else "user") or "user"
    return _identifier(scope_id, "global"), _identifier(actor_id, "user")


def _source_message_id(event: Any) -> str:
    message_obj = getattr(event, "message_obj", None)
    return _identifier(getattr(message_obj, "message_id", ""))


def _matching_session_state(
    session_store: Any | None,
    scope_id: str,
    actor_id: str,
    event: Any,
) -> Any | None:
    getter = getattr(session_store, "session", None)
    if not callable(getter):
        return None
    try:
        state = getter(scope_id, actor_id)
        event_text = str(event.get_message_str() or "")[:500]
    except Exception:  # noqa: BLE001
        return None
    latest_prompt = str(getattr(state, "latest_prompt", "") or "")
    return state if latest_prompt == event_text else None


def _task_id_from_event(event: Any, state: Any | None) -> str:
    for name in ("_plana_task_id", "_plana_run_id"):
        value = _identifier(getattr(event, name, ""))
        if value:
            return value
    behavior = getattr(event, "_plana_behavior_decision", None)
    delivery = getattr(behavior, "delivery_context", None)
    if isinstance(delivery, dict):
        task_id = _identifier(delivery.get("task_id"))
        if task_id:
            return task_id
    if state is None:
        return ""
    pending_id = _identifier(getattr(state, "latest_pending_run_id", ""))
    if pending_id:
        return pending_id
    return _identifier(getattr(state, "latest_remote_request_id", ""))


def _anchor_kind_from_event(event: Any, state: Any | None, task_id: str) -> str:
    explicit = _identifier(getattr(event, "_plana_anchor_kind", ""))
    if explicit:
        return explicit
    if state is not None and getattr(state, "latest_pending_run_id", None):
        return "pending_confirmation"
    profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
    if profile:
        return _identifier(f"{profile}_result")
    behavior = getattr(event, "_plana_behavior_decision", None)
    action = str(getattr(behavior, "action", "") or "")
    if task_id or action == "codex":
        return "task_result"
    return "assistant_message"


def _public_projection_from_event(
    event: Any,
    anchor_kind: str,
    task_id: str,
) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "anchor_kind": anchor_kind,
        "has_task": bool(task_id),
        "requires_owner_confirmation": anchor_kind == "pending_confirmation",
    }
    behavior = getattr(event, "_plana_behavior_decision", None)
    if behavior is not None:
        projection.update(
            {
                "route": str(getattr(behavior, "action", "") or ""),
                "capability": str(getattr(behavior, "capability", "") or ""),
                "risk_class": str(getattr(behavior, "risk_class", "") or ""),
                "media_intent": str(getattr(behavior, "media_intent", "") or ""),
            }
        )
    getter = getattr(event, "get_extra", None)
    if callable(getter):
        try:
            supplied = getter("_plana_public_projection", None)
        except TypeError:
            try:
                supplied = getter("_plana_public_projection")
            except Exception:  # noqa: BLE001
                supplied = None
        except Exception:  # noqa: BLE001
            supplied = None
        if isinstance(supplied, dict):
            projection.update(supplied)
    return sanitize_public_projection(projection)


def _decode_public_projection(value: Any) -> dict[str, Any]:
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return sanitize_public_projection(decoded)


def _identifier(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return (text or default)[:200]
