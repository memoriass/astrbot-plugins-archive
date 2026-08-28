from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "bili_workflow",
    "bili_search_up",
    "bili_add_dynamic_sub",
    "bili_add_live_sub",
    "bili_list_subs",
    "bili_remove_sub",
}
EXPECTED_COMMANDS = {
    "添加b站订阅",
    "添加b站直播",
    "取消b站订阅",
    "取消b站直播",
    "b站订阅列表",
    "b站登录",
    "b站登录状态",
    "b站搜索",
}
PLUGIN_NAME = "astrbot_plugin_bilibili_push"
EXPECTED_WEB_ENDPOINTS = {
    "accounts/delete",
    "accounts/upsert",
    "accounts/valid",
    "overview",
    "checks/live",
    "subscriptions/create",
    "subscriptions/delete",
    "subscriptions/enabled",
    "subscriptions/update",
    "pending/clear",
}
SKIP_LINE_LIMIT_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "env",
    "node_modules",
    "template_previews",
    "venv",
}


def main() -> None:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    commands, tools, custom_filters = _decorated_entries(tree)

    command_names = {name for _, name in commands}
    tool_names = {name for _, name in tools}
    missing_tools = EXPECTED_TOOLS - tool_names
    missing_commands = EXPECTED_COMMANDS - command_names
    if missing_tools:
        raise SystemExit(f"missing llm tools: {sorted(missing_tools)}")
    if missing_commands:
        raise SystemExit(f"missing commands: {sorted(missing_commands)}")
    if "bilibili_pending_shortcut" not in custom_filters:
        raise SystemExit("missing pending shortcut custom filter")
    if any("帮助" in name or "help" in func.lower() for func, name in commands):
        raise SystemExit("help command residue detected")
    _check_plugin_pages()
    _check_web_api_modules()
    _check_web_api_routes()

    oversized = _oversized_text_files()
    if oversized:
        details = ", ".join(f"{path}:{count}" for path, count in oversized)
        raise SystemExit(f"files over 500 lines: {details}")

    print("workflow_integration_check=ok")
    print("commands=" + ",".join(sorted(command_names)))
    print("tools=" + ",".join(sorted(tool_names)))
    routes = [f"/{PLUGIN_NAME}/{endpoint}" for endpoint in sorted(EXPECTED_WEB_ENDPOINTS)]
    print("web_routes=" + ",".join(routes))


def _decorated_entries(tree: ast.AST):
    commands = []
    tools = []
    custom_filters = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr == "command":
                name = (
                    deco.args[0].value
                    if deco.args and isinstance(deco.args[0], ast.Constant)
                    else ""
                )
                commands.append((node.name, name))
            elif deco.func.attr == "llm_tool":
                tools.append((node.name, _keyword_value(deco, "name")))
            elif deco.func.attr == "custom_filter":
                custom_filters.append(node.name)
    return commands, tools, custom_filters


def _keyword_value(call: ast.Call, name: str) -> str:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return ""


def _check_plugin_pages() -> None:
    required = [
        ROOT / "pages" / "manager" / "index.html",
        ROOT / "pages" / "manager" / "accounts.js",
        ROOT / "pages" / "manager" / "accounts.css",
        ROOT / "pages" / "manager" / "api.js",
        ROOT / "pages" / "manager" / "app.js",
        ROOT / "pages" / "manager" / "mock_bridge.js",
        ROOT / "pages" / "manager" / "overview.js",
        ROOT / "pages" / "manager" / "overview.css",
        ROOT / "pages" / "manager" / "renderers.js",
        ROOT / "pages" / "manager" / "style.css",
        ROOT / "pages" / "manager" / "subscriptions.js",
        ROOT / "pages" / "manager" / "subscriptions.css",
        ROOT / "pages" / "manager" / "utils.js",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing plugin page files: {missing}")


def _check_web_api_routes() -> None:
    source = (ROOT / "webapi" / "manager_api.py").read_text(encoding="utf-8")
    if PLUGIN_NAME not in source:
        raise SystemExit("missing plugin api route prefix")
    missing = [endpoint for endpoint in EXPECTED_WEB_ENDPOINTS if endpoint not in source]
    if missing:
        raise SystemExit(f"missing web api endpoints: {missing}")


def _check_web_api_modules() -> None:
    required = [
        ROOT / "webapi" / "manager_api.py",
        ROOT / "webapi" / "manager_crud.py",
        ROOT / "webapi" / "manager_overview.py",
        ROOT / "webapi" / "manager_response.py",
        ROOT / "webapi" / "manager_serializers.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing web api modules: {missing}")


def _oversized_text_files() -> list[tuple[str, int]]:
    oversized = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_LINE_LIMIT_DIRS for part in path.parts):
            continue
        try:
            count = sum(1 for _ in path.open("r", encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if count > 500:
            oversized.append((str(path.relative_to(ROOT)), count))
    return oversized


if __name__ == "__main__":
    main()
