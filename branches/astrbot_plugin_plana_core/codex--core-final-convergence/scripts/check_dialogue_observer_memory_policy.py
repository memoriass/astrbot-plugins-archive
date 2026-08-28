from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.observer import DialogueObserver


class Runtime:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def record_response(self, event, text) -> None:
        self.calls.append("record")

    async def extract_and_index_concepts(self, text, provider) -> None:
        self.calls.append("concept")

    async def extract_structured_memories(self, event, text, provider) -> None:
        self.calls.append("structured")

    async def update_mood_by_response(self, text, provider) -> None:
        self.calls.append("mood")


async def run() -> None:
    observer = DialogueObserver()
    chat_runtime = Runtime()
    chat_event = SimpleNamespace(
        _plana_behavior_decision=SimpleNamespace(action="direct_answer")
    )
    await observer.record_response(
        chat_runtime,
        chat_event,
        SimpleNamespace(completion_text="普通聊天回复"),
        None,
    )
    await asyncio.sleep(0)
    assert chat_runtime.calls == ["mood"], chat_runtime.calls

    task_runtime = Runtime()
    task_event = SimpleNamespace(
        _plana_behavior_decision=SimpleNamespace(action="native_tool")
    )
    await observer.record_response(
        task_runtime,
        task_event,
        SimpleNamespace(completion_text="任务结果"),
        None,
    )
    await asyncio.sleep(0)
    assert task_runtime.calls == ["record", "concept", "structured", "mood"], task_runtime.calls
    await observer.stop()


def main() -> int:
    asyncio.run(run())
    print("dialogue observer memory policy checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
