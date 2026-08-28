from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

astrbot = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_provider = types.ModuleType("astrbot.api.provider")
astrbot_provider.Provider = object
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", astrbot_api)
sys.modules.setdefault("astrbot.api.provider", astrbot_provider)

from astrbot_plugin_plana_core.prompt.builder import PromptBuilder


def main() -> int:
    builder = PromptBuilder()
    state = SimpleNamespace(
        mode="assistant",
        focus=0.8,
        pressure=0.2,
        risk_level="normal",
        mood_state="steady",
    )
    identity = SimpleNamespace(global_user_id="qq:10001", nickname="小明", role="user")
    context = SimpleNamespace(
        semantics=[],
        relations=[],
        memories=[
            SimpleNamespace(kind="message", content="用户最近在忙项目迁移"),
            SimpleNamespace(kind="message", content="我将调用执行部门，请稍候"),
        ],
    )
    chat = builder.build(state, identity, context, profile="chat", max_chars=1200)
    assert "PLANA_STATE" not in chat
    assert "TOOL_CONTEXT" not in chat
    assert "global_user_id" not in chat
    assert "执行部门" not in chat
    assert "用户最近在忙项目迁移" in chat
    task = builder.build(state, identity, context, profile="task", max_chars=1600)
    assert "PLANA_STATE" in task
    assert "TOOL_CONTEXT" in task
    print("conversational prompt profile checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
