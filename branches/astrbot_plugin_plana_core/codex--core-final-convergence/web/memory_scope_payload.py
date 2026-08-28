"""Build user-facing memory scope summaries for the dashboard."""

from __future__ import annotations

from typing import Any


def build_memory_scope_payload(runtime: Any, limit: int = 160) -> dict[str, object]:
    """Return active memory scopes with counts used by read-only Web selectors.

    Args:
        runtime: Active Plana runtime instance.
        limit: Maximum number of active scopes to expose.

    Returns:
        Stable scope summary payload for the embedded dashboard.
    """

    safe_limit = max(1, min(int(limit or 160), 200))
    raw_scopes = ["global"]
    active_scopes = getattr(runtime.storage, "active_memory_scopes", None)
    if callable(active_scopes):
        raw_scopes.extend(active_scopes(safe_limit))
    feedback_scopes = getattr(runtime.feedback_queue, "active_scope_ids", None)
    if callable(feedback_scopes):
        raw_scopes.extend(feedback_scopes(safe_limit))
    gap_scopes = getattr(runtime.recall_gap_tracker, "active_scope_ids", None)
    if callable(gap_scopes):
        raw_scopes.extend(gap_scopes(safe_limit))

    seen: set[str] = set()
    items: list[dict[str, object]] = []
    for raw_scope in raw_scopes:
        scope_id = str(raw_scope or "global").strip()[:200]
        if not scope_id or scope_id in seen:
            continue
        seen.add(scope_id)
        memory_counts = runtime.storage.memory_counts(scope_id, "")
        feedback_stats = runtime.feedback_queue.stats(scope_id)
        gap_stats = runtime.recall_gap_tracker.stats(scope_id)
        pending_feedback = sum(
            int(value)
            for key, value in feedback_stats.items()
            if str(key).endswith("_pending")
        )
        scope_kind, label = _scope_label(scope_id)
        items.append(
            {
                "id": scope_id,
                "label": label,
                "kind": scope_kind,
                "user_id": memory_scope_user_id(scope_id),
                "counts": {
                    "memories": int(memory_counts.get("episodic", 0)),
                    "semantics": int(memory_counts.get("semantic", 0)),
                    "active_atoms": int(memory_counts.get("active_atoms", 0)),
                    "pending_feedback": pending_feedback,
                    "open_gaps": int(gap_stats.get("open", 0)),
                },
            }
        )

    return {
        "summary": {
            "scopes": len(items),
            "memories": sum(int(item["counts"]["memories"]) for item in items),
            "semantics": sum(int(item["counts"]["semantics"]) for item in items),
            "pending_feedback": sum(int(item["counts"]["pending_feedback"]) for item in items),
            "open_gaps": sum(int(item["counts"]["open_gaps"]) for item in items),
        },
        "items": items,
    }


def _scope_label(scope_id: str) -> tuple[str, str]:
    if scope_id == "global":
        return "global", "\u5168\u5c40"
    parts = scope_id.split(":", 2)
    if len(parts) < 3:
        return "other", scope_id
    channel, event_type, identity = parts
    if event_type == "FriendMessage":
        if channel == "llonebot":
            return "friend", f"QQ \u597d\u53cb {identity}"
        if channel == "webchat":
            identity_parts = identity.split("!")
            owner = identity_parts[1] if len(identity_parts) > 1 else "user"
            session = identity_parts[-1][:8]
            owner_label = "\u672c\u5730\u7528\u6237" if owner == "root" else "\u672c\u5730\u6d4b\u8bd5" if owner.startswith("codex") else owner
            return "web", f"\u7f51\u9875\u4f1a\u8bdd \u00b7 {owner_label} \u00b7 {session}"
        return "friend", f"\u79c1\u804a\u4f1a\u8bdd {identity[:32]}"
    if event_type == "GroupMessage":
        user_id, _, group_id = identity.partition("_")
        return "group", f"\u7fa4\u804a {group_id or '-'} / \u7528\u6237 {user_id or '-'}"
    return "other", f"{channel} / {identity[:32]}"


def memory_scope_user_id(scope_id: str) -> str:
    """Resolve the profile identity represented by an AstrBot memory scope."""

    parts = str(scope_id or "").split(":", 2)
    if len(parts) < 3:
        return ""
    channel, event_type, identity = parts
    if channel == "llonebot" and event_type == "FriendMessage":
        return f"aiocqhttp:{identity}" if identity else ""
    if channel == "llonebot" and event_type == "GroupMessage":
        user_id, _, _group_id = identity.partition("_")
        return f"aiocqhttp:{user_id}" if user_id else ""
    if channel == "webchat" and event_type == "FriendMessage":
        identity_parts = identity.split("!")
        owner = identity_parts[1] if len(identity_parts) > 1 else ""
        return f"webchat:{owner}" if owner else ""
    return ""
