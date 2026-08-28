from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.dialogue import DialogueTurnAnalyzer  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    analyzer = DialogueTurnAnalyzer()
    catalog = {item["name"]: item for item in analyzer.action_catalog()}
    for retired in ("task_list", "workflow_list", "skill_candidate"):
        require(retired not in catalog, f"retired_action_present={retired}")
    cases = {
        "帮我搜索记忆里关于部署的内容": ("inject_prompt", "memory_query"),
        "show recent chat history": ("read_direct", "conversation_history"),
        "记住我喜欢深色主题": ("memory_write", "memory_write"),
        "创建一个待办：检查 beta 版本": ("codex_candidate", "tool_execution_candidate"),
        "Plana 创建一个只读测试工作流": ("codex_candidate", "tool_execution_candidate"),
        "plana 测试网络连接": ("codex_candidate", "tool_execution_candidate"),
        "清空所有记忆": ("reject", "unsupported_destructive"),
        "plana 今天状态如何？": ("status_query", "status_query"),
        "今天状态如何": ("inject_prompt", "chat"),
    }
    for text, expected in cases.items():
        decision = analyzer.analyze(text)
        require((decision.route, decision.intent) == expected, f"decision_mismatch={text}:{decision}")
    bridge = analyzer.analyze("检查日志", source="web_admin")
    require(bridge.intent == "tool_execution_candidate", "web_admin_not_codex_candidate")
    print("dialogue_analyzer_check=ok")


if __name__ == "__main__":
    main()
