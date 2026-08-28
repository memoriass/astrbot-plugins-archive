from __future__ import annotations

import secrets

from quart import request

from ..memory import ALL_MEMORY_KINDS, MEMORY_KIND_BRIDGE_HANDOFF
from ..web.auth import is_loopback_request


class PlanaPluginBridgeSupportMixin:
    def _remote_run(self, request_id: str) -> dict | None:
        if not request_id:
            return None
        store = getattr(self.runtime, "remote_task_runs", None)
        get = getattr(store, "get", None)
        if not callable(get):
            return None
        run = get(request_id)
        return run if isinstance(run, dict) else None

    def _remote_run_update(
        self,
        request_id: str,
        status: str,
        runner_run_id: str,
        payload: dict,
        error: str = "",
    ) -> str:
        if not request_id:
            return "missing"
        store = getattr(self.runtime, "remote_task_runs", None)
        apply_terminal = getattr(store, "apply_terminal_result", None)
        if callable(apply_terminal) and status in {"succeeded", "failed", "cancelled"}:
            return str(
                apply_terminal(
                    request_id,
                    status=status,
                    runner_run_id=runner_run_id,
                    error=error,
                    result=payload,
                )
            )
        update = getattr(store, "update", None)
        if callable(update):
            return "applied" if update(
                request_id,
                status=status,
                runner_run_id=runner_run_id,
                error=error,
                result=payload,
            ) else "missing"
        return "missing"

    def _remote_result_for_storage(self, payload: dict) -> dict:
        stored = dict(payload)
        stored.pop("retry_history", None)
        return stored

    def _remote_run_mark_submitted_if_nonterminal(
        self,
        request_id: str,
        runner_run_id: str,
        payload: dict,
    ) -> None:
        if not request_id:
            return
        store = getattr(self.runtime, "remote_task_runs", None)
        mark_submitted = getattr(store, "mark_submitted_if_nonterminal", None)
        if callable(mark_submitted):
            mark_submitted(
                request_id,
                runner_run_id=runner_run_id,
                result=payload,
            )

    def _handle_bridge_context_sync(
        self,
        scope_id: str,
        user_id: str,
        content: str,
        payload_data: dict,
        kind: str,
    ) -> dict[str, object]:
        queued = 0
        feedback_ids: list[int] = []
        for item in self._bridge_context_items(content, payload_data):
            feedback_id = self.runtime.feedback_queue.submit_new_memory(
                scope_id,
                user_id,
                str(item["content"]),
                kind=str(item["kind"]),
            )
            if feedback_id is not None:
                queued += 1
                feedback_ids.append(feedback_id)
        return {
            "kind": kind,
            "queued": queued > 0,
            "count": queued,
            "feedback_ids": feedback_ids,
        }

    def _bridge_context_items(
        self,
        content: str,
        payload_data: dict,
    ) -> list[dict[str, object]]:
        raw_items = (
            payload_data.get("memory_context")
            or payload_data.get("items")
            or payload_data.get("memories")
            or []
        )
        if isinstance(raw_items, (str, dict)):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            raw_items = []
        normalized = []
        if content:
            normalized.append(
                {
                    "kind": MEMORY_KIND_BRIDGE_HANDOFF,
                    "content": content[:1000],
                    "importance": 0.60,
                }
            )
        for item in raw_items[:8]:
            if isinstance(item, dict):
                text = str(
                    item.get("content")
                    or item.get("text")
                    or item.get("summary")
                    or ""
                ).strip()
                memory_kind = str(item.get("kind") or MEMORY_KIND_BRIDGE_HANDOFF)
                importance = self._bridge_float(item.get("importance", 0.58), 0.58)
            else:
                text = str(item).strip()
                memory_kind = MEMORY_KIND_BRIDGE_HANDOFF
                importance = 0.58
            if text:
                normalized.append(
                    {
                        "kind": memory_kind[:80],
                        "content": text[:1000],
                        "importance": min(max(importance, 0.0), 1.0),
                    }
                )
        return normalized[:8]

    def _bridge_limit(self, value: object, maximum: int) -> int:
        limit = self._bridge_int(value, 8)
        return max(1, min(limit, maximum))

    def _bridge_int(self, value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _bridge_float(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _bridge_success(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        return text not in {"0", "false", "failed", "error", "no"}

    def _bridge_target_kinds(self, payload_data: dict) -> list[str]:
        raw = payload_data.get("target_kinds") or payload_data.get("kinds") or []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raw = []
        if payload_data.get("kind"):
            raw.append(str(payload_data.get("kind")))
        result = []
        for item in raw:
            kind = str(item).strip()
            if kind in ALL_MEMORY_KINDS and kind not in result:
                result.append(kind)
        return result[:6]

    def _search_bridge_memories(
        self,
        scope_id: str,
        query: str,
        target_kinds: list[str],
        limit: int,
    ):
        kernel = getattr(self.runtime, "memory_kernel", None)
        if not target_kinds:
            if kernel is not None:
                return kernel.search(scope_id, query, "", limit)["memories"]
            if query:
                return self.runtime.storage.search_memories(scope_id, query, limit)
            return self.runtime.storage.recent_memories(scope_id, limit)
        items = []
        seen = set()
        for memory_kind in target_kinds:
            if kernel is not None:
                candidates = kernel.search(scope_id, query, memory_kind, limit)[
                    "memories"
                ]
            else:
                candidates = (
                    self.runtime.storage.search_memories_by_kind(
                        scope_id, query, memory_kind, limit
                    )
                    if query
                    else self.runtime.storage.recent_memories_by_kind(
                        scope_id, memory_kind, limit
                    )
                )
            for item in candidates:
                if item.id not in seen:
                    seen.add(item.id)
                    items.append(item)
        items.sort(key=lambda item: (item.importance, item.created_at), reverse=True)
        return items[:limit]

    def _bridge_memory_item(self, item) -> dict[str, object]:
        return {
            "id": item.id,
            "kind": item.kind,
            "content": item.content,
            "importance": round(item.importance, 3),
            "source": item.source,
            "created_at": item.created_at,
        }

    def _bridge_authorized(self) -> bool:
        if is_loopback_request(request):
            return True
        return self._token_authorized(self.bridge_api_token)

    def _token_authorized(self, expected_token: str) -> bool:
        if not expected_token:
            return False
        token = request.headers.get("X-Plana-Token", "").strip()
        if not token:
            token = (
                request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            )
        return secrets.compare_digest(token, expected_token)
