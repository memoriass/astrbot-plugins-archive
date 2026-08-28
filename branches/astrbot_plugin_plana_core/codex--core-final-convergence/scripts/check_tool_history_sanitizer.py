from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue.tool_policy import _scrub_context_tool_history


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    request = SimpleNamespace(
        contexts=[
            {
                "role": "assistant",
                "content": "orphan",
                "tool_calls": [
                    {
                        "id": "orphan-1",
                        "function": {"name": "plana_recall_memory"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "paired",
                "tool_calls": [
                    {
                        "id": "paired-1",
                        "function": {"name": "plana_recall_memory"},
                    }
                ],
            },
            {
                "role": "tool",
                "name": "plana_recall_memory",
                "tool_call_id": "paired-1",
                "content": "ok",
            },
        ]
    )
    _scrub_context_tool_history(request, {"plana_recall_memory"})
    require(len(request.contexts) == 3, f"unexpected_context_count={request.contexts}")
    require(request.contexts[0] == {"role": "assistant", "content": "orphan"}, "orphan_not_flattened")
    require(request.contexts[1]["tool_calls"][0]["id"] == "paired-1", "paired_call_missing")
    require(request.contexts[2]["tool_call_id"] == "paired-1", "paired_result_missing")
    print("tool_history_sanitizer_check=ok")


if __name__ == "__main__":
    main()
