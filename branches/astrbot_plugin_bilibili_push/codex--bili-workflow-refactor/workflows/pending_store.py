from __future__ import annotations

import time


KV_KEY = "bili_workflow_pending_tasks"


class PendingTaskStore:
    def __init__(self, star, ttl_sec: int):
        self.star = star
        self.ttl_sec = int(ttl_sec)
        self._tasks: dict[str, dict] = {}
        self._loaded = False

    async def ensure_loaded(self) -> None:
        if self._loaded:
            if self._cleanup_expired():
                await self._save()
            return
        data = await self.star.get_kv_data(KV_KEY, {})
        self._tasks = data if isinstance(data, dict) else {}
        self._loaded = True
        if self._cleanup_expired():
            await self._save()

    async def create(self, task: dict) -> str:
        await self.ensure_loaded()
        task_id = str(task["task_id"])
        task["expires_at"] = time.time() + self.ttl_sec
        self._tasks[task_id] = task
        await self._save()
        return task_id

    async def get(self, task_id: str) -> dict | None:
        await self.ensure_loaded()
        return self._tasks.get(task_id)

    async def delete(self, task_id: str) -> None:
        await self.ensure_loaded()
        self._tasks.pop(task_id, None)
        await self._save()

    async def clear(self) -> int:
        await self.ensure_loaded()
        count = len(self._tasks)
        self._tasks.clear()
        await self._save()
        return count

    async def list_tasks(self) -> list[dict]:
        await self.ensure_loaded()
        return list(self._tasks.values())

    async def resolve(self, task_ref: str, origin: str = "") -> tuple[str, list[str]]:
        await self.ensure_loaded()
        ref = str(task_ref or "").lower()
        fragment = ref.removeprefix("bili")
        matches = []
        for task_id, task in self._tasks.items():
            if origin and task.get("origin") != origin:
                continue
            if task_id == ref or task_id.startswith(ref):
                matches.append(task_id)
            elif len(fragment) >= 3 and task_id.removeprefix("bili").endswith(fragment):
                matches.append(task_id)
        if len(matches) == 1:
            return matches[0], []
        if len(matches) > 1:
            return "", matches
        return "", []

    async def _save(self) -> None:
        await self.star.put_kv_data(KV_KEY, self._tasks)

    def _cleanup_expired(self) -> bool:
        now = time.time()
        expired = [
            task_id
            for task_id, task in self._tasks.items()
            if float(task.get("expires_at") or 0) < now
        ]
        for task_id in expired:
            self._tasks.pop(task_id, None)
        return bool(expired)
