from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import time
from typing import Any


JobHandler = Callable[[], Awaitable[None]]


class RuntimeJobManager:
    """Small lifecycle-owned async job manager for Plana background loops."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: JobHandler,
        *,
        interval_seconds: int,
        enabled: bool = True,
    ) -> None:
        self._jobs[name] = {
            "name": name,
            "handler": handler,
            "interval_seconds": max(1, int(interval_seconds)),
            "enabled": bool(enabled),
            "task": None,
            "running": False,
            "last_started_at": 0,
            "last_finished_at": 0,
            "last_error": "",
            "run_count": 0,
        }

    def start_all(self) -> None:
        for job in self._jobs.values():
            if not job["enabled"] or job.get("task") is not None:
                continue
            job["task"] = asyncio.get_event_loop().create_task(self._loop(job))

    async def stop_all(self) -> None:
        tasks = []
        for job in self._jobs.values():
            task = job.get("task")
            if task is not None and not task.done():
                task.cancel()
                tasks.append(task)
            job["task"] = None
            job["running"] = False
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run_once(self, name: str) -> dict[str, Any]:
        job = self._jobs.get(name)
        if job is None:
            return {"ok": False, "error": "job_not_found"}
        await self._run(job)
        return {"ok": not bool(job["last_error"]), "job": self._public(job)}

    def status(self) -> dict[str, Any]:
        return {name: self._public(job) for name, job in sorted(self._jobs.items())}

    async def _loop(self, job: dict[str, Any]) -> None:
        while True:
            try:
                await asyncio.sleep(int(job["interval_seconds"]))
                await self._run(job)
            except asyncio.CancelledError:
                raise

    async def _run(self, job: dict[str, Any]) -> None:
        job["running"] = True
        job["last_started_at"] = int(time())
        job["last_error"] = ""
        try:
            await job["handler"]()
            job["run_count"] = int(job["run_count"]) + 1
        except Exception as exc:  # noqa: BLE001
            job["last_error"] = str(exc)[:500]
        finally:
            job["running"] = False
            job["last_finished_at"] = int(time())

    def _public(self, job: dict[str, Any]) -> dict[str, Any]:
        task = job.get("task")
        return {
            "enabled": bool(job["enabled"]),
            "interval_seconds": int(job["interval_seconds"]),
            "running": bool(job["running"]),
            "active": task is not None and not task.done(),
            "last_started_at": int(job["last_started_at"]),
            "last_finished_at": int(job["last_finished_at"]),
            "last_error": str(job["last_error"]),
            "run_count": int(job["run_count"]),
        }
