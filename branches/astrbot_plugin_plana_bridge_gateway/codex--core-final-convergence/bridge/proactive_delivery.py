from __future__ import annotations

import time
import uuid
from typing import Any, Awaitable, Callable

from .codex_relay import CodexRunnerRelay, DeliveryResult

PostJson = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


async def deliver_proactive_tasks(
    tasks: list[dict[str, Any]],
    *,
    codex_relay: CodexRunnerRelay,
    nacho_enabled: bool,
    post_to_nacho: PostJson,
) -> list[int]:
    if not tasks:
        return []
    results = await deliver_proactive_task_results(
        tasks,
        codex_relay=codex_relay,
        nacho_enabled=nacho_enabled,
        post_to_nacho=post_to_nacho,
    )
    return [item.task_id for item in results if item.ok and item.task_id > 0]


async def deliver_proactive_task_results(
    tasks: list[dict[str, Any]],
    *,
    codex_relay: CodexRunnerRelay,
    nacho_enabled: bool,
    post_to_nacho: PostJson,
) -> list[DeliveryResult]:
    if not tasks:
        return []
    results = await codex_relay.deliver_tasks(tasks)
    nacho_tasks = [task for task in tasks if not codex_relay.is_codex_task(task)]
    if not nacho_tasks or not nacho_enabled:
        return results
    payload = {
        "event_id": f"proactive-{uuid.uuid4()}",
        "timestamp": int(time.time()),
        "proactive_tasks": nacho_tasks,
    }
    data = await post_to_nacho(payload)
    if isinstance(data, dict) and data.get("ok", True):
        results.extend(
            DeliveryResult(task_id=_task_id(task), ok=True)
            for task in nacho_tasks
            if _task_id(task) > 0
        )
    else:
        results.extend(
            DeliveryResult(
                task_id=_task_id(task),
                ok=False,
                error="nacho_delivery_failed",
            )
            for task in nacho_tasks
            if _task_id(task) > 0
        )
    return results


def _task_id(task: dict[str, Any]) -> int:
    try:
        return int(task.get("id", 0) or 0)
    except (TypeError, ValueError):
        return 0
