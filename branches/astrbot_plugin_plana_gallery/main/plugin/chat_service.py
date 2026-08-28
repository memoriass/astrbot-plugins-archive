from __future__ import annotations

from typing import Any

from ..assets import CHAT_CONTRACT_VERSION, CHAT_FEEDBACK_VERSION, GalleryStore


class GalleryChatService:
    """Controlled chat-facing service shared by HTTP and sibling plugins."""

    def __init__(self, store: GalleryStore) -> None:
        self.store = store

    def candidates(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("contract_version") != CHAT_CONTRACT_VERSION:
            return {
                "ok": False,
                "error": "contract_version_mismatch",
                "contract_version": CHAT_CONTRACT_VERSION,
            }
        candidates = self.store.chat_candidates(
            request_id=str(payload.get("request_id") or ""),
            query=str(payload.get("query") or ""),
            facets=_string_list(payload.get("facets"), 12),
            emotions=_emotion_list(payload.get("emotions"), 4),
            exclude_asset_refs=_string_list(payload.get("exclude_asset_refs"), 100),
            limit=_safe_int(payload.get("limit"), 6, 1, 12),
        )
        return {
            "ok": True,
            "contract_version": CHAT_CONTRACT_VERSION,
            "request_id": str(payload.get("request_id") or "")[:160],
            "candidates": candidates,
        }

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        version = str(payload.get("contract_version") or CHAT_FEEDBACK_VERSION)
        if version != CHAT_FEEDBACK_VERSION:
            return {
                "ok": False,
                "error": "contract_version_mismatch",
                "contract_version": CHAT_FEEDBACK_VERSION,
            }
        result = self.store.record_chat_feedback(
            event_id=str(payload.get("event_id") or ""),
            request_id=str(payload.get("request_id") or ""),
            asset_ref=str(payload.get("asset_ref") or ""),
            event=str(payload.get("event") or ""),
            query=str(payload.get("query") or ""),
            reason=str(payload.get("reason") or ""),
        )
        result["contract_version"] = CHAT_FEEDBACK_VERSION
        return result

    def resolve(self, asset_ref: str) -> dict[str, Any]:
        result = self.store.resolve_chat_asset(str(asset_ref or ""))
        result["contract_version"] = CHAT_CONTRACT_VERSION
        return result

    def status(self) -> dict[str, Any]:
        state = self.store.status()
        return {
            "ok": True,
            "contract_version": CHAT_CONTRACT_VERSION,
            "assets": int(state.get("asset_count", 0) or 0),
            "needs_review": int(state.get("needs_review_count", 0) or 0),
            "transport": "in_process",
        }


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:160] for item in value[:limit] if str(item).strip()]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _emotion_list(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("emotion_tag") or item.get("tag") or "").strip().lower()[:80]
        if not tag.startswith("emotion:"):
            continue
        result.append(
            {
                "emotion_tag": tag,
                "target_intensity": _safe_int(
                    item.get("target_intensity") or item.get("intensity"), 2, 1, 3
                ),
                "weight": item.get("weight", 1.0),
                "prominence": (
                    "primary" if str(item.get("prominence")) == "primary" else "secondary"
                ),
            }
        )
    return result
