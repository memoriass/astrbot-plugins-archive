from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from astrbot.api import logger
from .codex_relay import DeliveryResult

PollTasks = Callable[[int], Awaitable[list[dict[str, Any]]]]
DeliverTasks = Callable[[list[dict[str, Any]]], Awaitable[list[DeliveryResult]]]
MarkDelivered = Callable[[int, str, str, bool], Awaitable[bool]]
MarkFailed = Callable[[int, str, str, str], Awaitable[bool]]


class ProactiveDeliveryLoop:
    def __init__(
        self,
        *,
        enabled: bool,
        interval_seconds: int,
        poll: PollTasks,
        deliver: DeliverTasks,
        mark: MarkDelivered,
        mark_failed: MarkFailed,
    ) -> None:
        self.enabled = enabled
        self.interval_seconds = max(2, min(int(interval_seconds or 10), 300))
        self._poll = poll
        self._deliver = deliver
        self._mark = mark
        self._mark_failed = mark_failed
        self._task: asyncio.Task | None = None
        self._last_delivery: dict[str, Any] = {}

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="plana_bridge_proactive_loop")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._task is not None and not self._task.done(),
            "interval_seconds": self.interval_seconds,
            "last_delivery": dict(self._last_delivery),
        }

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana Bridge proactive delivery loop failed: %s", exc)

    async def _tick(self) -> None:
        tasks = await self._poll(5)
        if not tasks:
            return
        results = await self._deliver(tasks)
        delivered = 0
        failed = 0
        for result in results:
            if result.ok:
                if await self._mark(
                    result.task_id,
                    result.request_id,
                    result.runner_run_id,
                    result.result_finalized,
                ):
                    delivered += 1
                continue
            failed += 1
            await self._mark_failed(
                result.task_id,
                result.error,
                result.request_id,
                result.runner_run_id,
            )
        self._last_delivery = {
            "polled": len(tasks),
            "delivered": delivered,
            "failed": failed,
        }
