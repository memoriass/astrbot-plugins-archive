from __future__ import annotations

import ast
import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    ROOT / "__init__.py",
    ROOT / "main.py",
    ROOT / "core",
    ROOT / "tools",
    ROOT / "workflows",
    ROOT / "rendering",
)
FORBIDDEN_IMPORTS = {"astrbot.api.web"}
REQUIRED_PAGE_PREFIXES = {"/ncqq_manager", "/astrbot_plugin_ncqq_manager"}
HEALTH_WORKFLOW_IDS = {
    "check_health",
    "check_manager",
    "check_botshepherd",
    "check_bot_runtime",
    "health",
    "health_check",
    "manager_health",
    "botshepherd_health",
    "bot_runtime_health",
}


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in SOURCE_PATHS:
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(path.rglob("*.py")))
    return files


def _parse(path: pathlib.Path) -> ast.Module:
    try:
        return ast.parse(_read(path), filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)} has invalid Python syntax: {exc}") from exc


def _metadata_version() -> str:
    match = re.search(r"^version:\s*([^\s#]+)\s*$", _read(ROOT / "metadata.yaml"), re.MULTILINE)
    if not match:
        raise AssertionError("metadata.yaml is missing version")
    return match.group(1)


def _register_version() -> str:
    tree = _parse(ROOT / "main.py")
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            is_register = isinstance(func, ast.Name) and func.id == "register"
            if is_register and len(decorator.args) >= 4:
                version = decorator.args[3]
                if isinstance(version, ast.Constant) and isinstance(version.value, str):
                    return version.value
    raise AssertionError("main.py is missing @register(..., version, ...)")


def _check_versions(errors: list[str]) -> None:
    metadata_version = _metadata_version()
    register_version = _register_version()
    if metadata_version != register_version:
        errors.append(
            f"version mismatch: metadata.yaml={metadata_version}, main.py={register_version}"
        )


def _check_forbidden_imports(errors: list[str]) -> None:
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_IMPORTS:
                        errors.append(f"{path.relative_to(ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in FORBIDDEN_IMPORTS:
                    errors.append(f"{path.relative_to(ROOT)} imports from {module}")


def _dict_literal_keys(tree: ast.Module, name: str) -> set[str]:
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Dict):
            raise AssertionError(f"{name} must be a dict literal")
        keys: set[str] = set()
        for key in value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
        return keys
    raise AssertionError(f"{name} not found")


def _check_health_workflows(errors: list[str]) -> None:
    keys = _dict_literal_keys(_parse(ROOT / "workflows" / "models.py"), "COMPILED_WORKFLOWS")
    exposed = sorted(keys & HEALTH_WORKFLOW_IDS)
    if exposed:
        errors.append("health workflows are externally registered: " + ", ".join(exposed))


def _check_page_api(errors: list[str]) -> None:
    tree = _parse(ROOT / "tools" / "page_api.py")
    prefixes: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "PLUGIN_ROUTE_PREFIXES"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Tuple):
            prefixes = {
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    missing = sorted(REQUIRED_PAGE_PREFIXES - prefixes)
    if missing:
        errors.append("missing page api prefixes: " + ", ".join(missing))


def _check_json(errors: list[str]) -> None:
    try:
        json.loads(_read(ROOT / "_conf_schema.json"))
    except json.JSONDecodeError as exc:
        errors.append(f"_conf_schema.json is invalid: {exc}")


def main() -> int:
    errors: list[str] = []
    checks = (
        _check_versions,
        _check_forbidden_imports,
        _check_health_workflows,
        _check_page_api,
        _check_json,
    )
    for check in checks:
        try:
            check(errors)
        except AssertionError as exc:
            errors.append(str(exc))

    if errors:
        print("release verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("release verification ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
