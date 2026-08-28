from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import types


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
    "accounts/qr/poll",
    "accounts/qr/start",
    "accounts/upsert",
    "accounts/valid",
    "bilibili/user",
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
    required_filters = {"bilibili_pending_shortcut", "bilibili_natural_workflow"}
    missing_filters = required_filters - set(custom_filters)
    if missing_filters:
        raise SystemExit(f"missing custom filters: {sorted(missing_filters)}")
    if any("帮助" in name or "help" in func.lower() for func, name in commands):
        raise SystemExit("help command residue detected")
    _check_plugin_pages()
    _check_rendering_resources()
    _check_runtime_guards()
    _check_ai_workflow_modules()
    _check_alias_schema()
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
        ROOT / "pages" / "manager" / "account_qr.js",
        ROOT / "pages" / "manager" / "api.js",
        ROOT / "pages" / "manager" / "app.js",
        ROOT / "pages" / "manager" / "mock_bridge.js",
        ROOT / "pages" / "manager" / "overview.js",
        ROOT / "pages" / "manager" / "overview.css",
        ROOT / "pages" / "manager" / "renderers.js",
        ROOT / "pages" / "manager" / "style.css",
        ROOT / "pages" / "manager" / "subscriptions.js",
        ROOT / "pages" / "manager" / "subscriptions.css",
        ROOT / "pages" / "manager" / "subscription_identity.js",
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


def _check_rendering_resources() -> None:
    required = [
        ROOT / "utils" / "image_optimizer.py",
        ROOT / "utils" / "resources" / "fonts" / "noto-sans-sc-chinese-simplified-400-normal.woff2",
        ROOT / "utils" / "resources" / "fonts" / "noto-sans-sc-chinese-simplified-700-normal.woff2",
        ROOT / "utils" / "resources" / "fonts" / "NotoSansSC-LICENSE.txt",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing rendering resources: {missing}")

    renderer = (ROOT / "utils" / "html_renderer.py").read_text(encoding="utf-8")
    resource = (ROOT / "utils" / "resource.py").read_text(encoding="utf-8")
    movie_card = (ROOT / "utils" / "renderers" / "movie_card.py").read_text(
        encoding="utf-8"
    )
    dynamic_card = (ROOT / "utils" / "renderers" / "dynamic_card.py").read_text(
        encoding="utf-8"
    )
    if "_RENDER_RETRIES = 1" not in renderer or "BrowserManager.recycle" not in renderer:
        raise SystemExit("html renderer retry/recycle guard is missing")
    if "localize_template_avatar_images" not in renderer or "avatar_cache_dir" not in renderer:
        raise SystemExit("html renderer avatar local cache is missing")
    if "get_internal_font_routes" not in resource or "BiliPushNotoSansSC" not in resource:
        raise SystemExit("internal font resource wiring is missing")
    if (
        "optimize_template_image" not in movie_card
        or "DYNAMIC_HERO_POLICY" not in movie_card
        or "avatar_cache_dir" not in movie_card
    ):
        raise SystemExit("push card cover optimization is missing")
    if "dynamic_card.html.jinja" in dynamic_card:
        raise SystemExit("dynamic card theme points to a removed template")
    if "dynamic_movie_card.html.jinja" not in dynamic_card:
        raise SystemExit("dynamic card theme does not reuse the existing dynamic template")

    template_dir = ROOT / "utils" / "resources" / "templates"
    forbidden_remote_assets = [
        "http://i0.hdslb.com/bfs/face/member/noface.jpg",
        "https://www.bilibili.com/favicon.ico",
    ]
    for path in template_dir.glob("*.jinja"):
        source = path.read_text(encoding="utf-8")
        for asset in forbidden_remote_assets:
            if asset in source:
                raise SystemExit(
                    f"remote fallback asset in template {path.relative_to(ROOT)}: {asset}"
                )


def _check_runtime_guards() -> None:
    avatar_cache = (ROOT / "core" / "avatar_cache.py").read_text(encoding="utf-8")
    for required in (
        "bili_avatar_cache",
        "FETCH_CONCURRENCY",
        "UNUSED_RETENTION_SEC",
        "REFRESH_AFTER_SEC = 24 * 3600",
        "fetch_avatar_map",
        "async with _fetch_semaphore",
    ):
        if required not in avatar_cache:
            raise SystemExit(f"avatar cache guard missing: {required}")

    live_checker = (ROOT / "scheduler" / "live_checker.py").read_text(encoding="utf-8")
    if "not current_is_first or self.push_on_startup" not in live_checker:
        raise SystemExit("live cold-start push guard is missing")

    for path in (
        ROOT / "webapi" / "manager_overview.py",
        ROOT / "workflows" / "cards.py",
        ROOT / "handlers" / "subscription_list.py",
    ):
        source = path.read_text(encoding="utf-8")
        if "fetch_avatar_map" not in source:
            raise SystemExit(f"avatar cache is not used by {path.relative_to(ROOT)}")


def _check_web_api_modules() -> None:
    required = [
        ROOT / "webapi" / "manager_api.py",
        ROOT / "webapi" / "manager_crud.py",
        ROOT / "webapi" / "manager_login.py",
        ROOT / "webapi" / "manager_overview.py",
        ROOT / "webapi" / "manager_response.py",
        ROOT / "webapi" / "manager_serializers.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing web api modules: {missing}")


def _check_ai_workflow_modules() -> None:
    required = [
        ROOT / "workflows" / "branches.py",
        ROOT / "workflows" / "dispatch.py",
        ROOT / "workflows" / "entity_resolver.py",
        ROOT / "workflows" / "resolver_stats.py",
        ROOT / "workflows" / "workflow-map.md",
        ROOT / "workflows" / "workflow-map.mmd",
        ROOT / "workflows" / "workflow-map.drawio",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing ai workflow modules: {missing}")

    models = (ROOT / "workflows" / "models.py").read_text(encoding="utf-8")
    runner = (ROOT / "workflows" / "runner.py").read_text(encoding="utf-8")
    if "ai_dispatch" not in models or "ai_dispatch" not in runner:
        raise SystemExit("ai_dispatch workflow is not registered")
    if "REMOVE_CONFIRM_REPLIES" not in models:
        raise SystemExit("remove confirmation replies are not defined")
    for workflow in (
        "find_subscription",
        "diagnose_health",
        "diagnose_resolver",
        "check_live_current_group",
        "check_live_all_groups",
    ):
        if workflow not in models or workflow not in runner:
            raise SystemExit(f"{workflow} workflow is not registered")

    visible_task_text = (
        ROOT / "workflows" / "subscription.py"
    ).read_text(encoding="utf-8") + (
        ROOT / "workflows" / "search.py"
    ).read_text(encoding="utf-8")
    forbidden = ("任务ID:", "发送 `bili{task_id")
    if any(item in visible_task_text for item in forbidden):
        raise SystemExit("visible pending task id text residue detected")
    if "confirm_remove_subscription" not in visible_task_text:
        raise SystemExit("remove workflow confirmation task is missing")
    ai_handler = (ROOT / "handlers" / "ai_handler.py").read_text(encoding="utf-8")
    if 'workflow", "") == "search_up"' in ai_handler:
        raise SystemExit("search_up cards are still suppressed unconditionally")
    if "_should_present_tool_result" not in ai_handler:
        raise SystemExit("llm tool foreground presentation gate is missing")
    pending = (ROOT / "workflows" / "pending.py").read_text(encoding="utf-8")
    parsing_pending = (ROOT / "workflows" / "parsing_pending.py").read_text(
        encoding="utf-8"
    )
    if "looks_like_standalone_pending_action" not in pending + parsing_pending:
        raise SystemExit("standalone pending continuation fallback is missing")
    _check_natural_dispatch_boundaries()


def _check_natural_dispatch_boundaries() -> None:
    modules = _load_workflow_parse_modules()
    workflow_from_natural_language = modules[
        "parsing_natural"
    ].workflow_from_natural_language
    build_dispatch_branches = modules["branches"].build_dispatch_branches

    blocked = (
        "plana检查一下本机插件使用的playwright与mcp playwright会不会互锁，本机插件html出现渲染超时",
        "检查一下本机插件日志",
        "b站插件健康诊断",
        "Bilibili插件健康诊断",
        "检查一下bilibili插件状态",
    )
    for text in blocked:
        request = workflow_from_natural_language(text)
        branches = build_dispatch_branches(text, require_context=True)
        if request is not None or branches:
            raise SystemExit(f"non-public text entered bili dispatch: {text}")


def _load_workflow_parse_modules():
    package = types.ModuleType("workflows")
    package.__path__ = [str(ROOT / "workflows")]
    sys.modules["workflows"] = package

    loaded = {}
    for name in ("utils", "models", "branch_readonly", "branches", "parsing_natural"):
        path = ROOT / "workflows" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"workflows.{name}", path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"cannot load workflow module: {name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"workflows.{name}"] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


def _check_alias_schema() -> None:
    schema = (ROOT / "database" / "schema.py").read_text(encoding="utf-8")
    manager = (ROOT / "database" / "db_manager.py").read_text(encoding="utf-8")
    aliases = (ROOT / "database" / "aliases.py").read_text(encoding="utf-8")
    resolver = (ROOT / "workflows" / "entity_resolver.py").read_text(encoding="utf-8")
    if "up_aliases" not in schema:
        raise SystemExit("up_aliases schema is missing")
    if "up_alias_evidence" not in schema:
        raise SystemExit("up_alias_evidence schema is missing")
    if "AliasStoreMixin" not in manager:
        raise SystemExit("DatabaseManager does not include AliasStoreMixin")
    if "find_shared_up_aliases" not in aliases or "upsert_up_alias_evidence" not in aliases:
        raise SystemExit("shared alias evidence store is missing")
    if "_shared_alias_candidates" not in resolver or "alias:shared" not in resolver:
        raise SystemExit("shared alias resolver layer is missing")


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
