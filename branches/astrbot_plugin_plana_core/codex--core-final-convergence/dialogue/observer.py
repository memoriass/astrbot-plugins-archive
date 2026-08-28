from __future__ import annotations

import asyncio
from typing import Any

try:
    from astrbot.api import logger
except ModuleNotFoundError:  # pragma: no cover - used by standalone checks
    import logging

    logger = logging.getLogger(__name__)


class DialogueObserver:
    """Observe incoming messages and LLM responses for memory side effects."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    async def stop(self) -> None:
        if not self._tasks:
            return
        for task in tuple(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def ingest_event(self, runtime: Any, event: Any) -> None:
        try:
            runtime.ingest_event(event)
        except Exception:  # noqa: BLE001
            logger.warning("Plana message memory observe failed", exc_info=True)

    async def record_response(self, runtime: Any, event: Any, response: Any, provider: Any) -> None:
        text = str(getattr(response, "completion_text", "") or "")
        if not text.strip():
            return
        if bool(getattr(event, "_plana_skip_response_memory", False)):
            logger.info("Plana response memory skipped: reason=live_search_result")
            return
        behavior = getattr(event, "_plana_behavior_decision", None)
        action = str(getattr(behavior, "action", "") or "")
        ordinary_chat = action in {"direct_answer", "silence"}
        if not ordinary_chat:
            try:
                runtime.record_response(event, text)
            except Exception:  # noqa: BLE001
                logger.warning("Plana response memory write failed", exc_info=True)
        task = asyncio.create_task(
            self._record_response_side_effects(
                runtime,
                event,
                text,
                provider,
                ordinary_chat=ordinary_chat,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_task_error)

    async def _record_response_side_effects(
        self,
        runtime: Any,
        event: Any,
        text: str,
        provider: Any,
        *,
        ordinary_chat: bool = False,
    ) -> None:
        operations = [("mood update", lambda: runtime.update_mood_by_response(text, provider))]
        if not ordinary_chat:
            operations[:0] = [
                ("concept extraction", lambda: runtime.extract_and_index_concepts(text, provider)),
                ("structured memory extraction", lambda: runtime.extract_structured_memories(event, text, provider)),
            ]
        for label, operation in operations:
            try:
                await operation()
            except Exception:  # noqa: BLE001
                logger.warning("Plana %s failed", label, exc_info=True)

    def _log_task_error(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            logger.warning("Plana response observer task failed", exc_info=True)
