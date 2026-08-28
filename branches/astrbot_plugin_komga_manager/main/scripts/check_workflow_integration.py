from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READS = {
    "list_libraries",
    "list_recent",
    "search_series",
    "series_detail",
    "list_books",
    "on_deck",
    "collections",
    "readlists",
}
WRITES = {
    "scan_library",
    "analyze_library",
    "refresh_library_metadata",
    "refresh_series_metadata",
}


def main() -> None:
    required = {
        "main.py",
        "metadata.yaml",
        "_conf_schema.json",
        "README.md",
        "ARCHITECTURE.md",
        "requirements.txt",
        "integrations/komga.py",
        "workflows/models.py",
        "workflows/runner.py",
        "workflows/proposals.py",
    }
    missing = sorted(path for path in required if not (ROOT / path).exists())
    require(not missing, f"missing files: {missing}")

    main_source = read("main.py")
    main_tree = ast.parse(main_source)
    require(_decorated(main_tree, "llm_tool") == {"komga_manager"}, "tool registration mismatch")
    require(_decorated(main_tree, "command") == {"komga"}, "command registration mismatch")
    require("domain_harness_descriptors" not in main_source, "main branch contains domain descriptor")
    require("propose_domain_action" not in main_source, "main branch contains domain proposal facade")
    require(not _imports_plana_core(), "plugin imports Plana Core")

    metadata = read("metadata.yaml")
    require(re.search(r"(?m)^name:\s*astrbot_plugin_komga_manager\s*$", metadata), "metadata name mismatch")
    version = re.search(r"(?m)^version:\s*([^\s#]+)", metadata)
    require(version is not None and f'"{version.group(1)}"' in main_source, "version mismatch")
    json.loads(read("_conf_schema.json"))

    models = _module_values(ROOT / "workflows" / "models.py")
    require(set(models["READ_WORKFLOWS"]) == READS, "read workflow set mismatch")
    require(set(models["WRITE_WORKFLOWS"]) == WRITES, "write workflow set mismatch")

    client_source = read("integrations/komga.py")
    for marker in (".post(", ".put(", ".patch(", ".delete("):
        require(marker not in client_source, f"mutation HTTP method present: {marker}")
    for operation in WRITES:
        require(f"def {operation}" not in client_source, f"write client method present: {operation}")
    proposal_source = read("workflows/proposals.py")
    require('"action": "write_pending"' in proposal_source, "write_pending proposal missing")
    require('"executed": False' in proposal_source, "write proposal execution guard missing")

    oversized = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        lines = sum(1 for _line in path.open("r", encoding="utf-8"))
        if lines > 500:
            oversized.append(f"{path.relative_to(ROOT)}:{lines}")
    require(not oversized, "files over 500 lines: " + ", ".join(oversized))
    print("komga_workflow_integration_check=ok")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _imports_plana_core() -> bool:
    for path in ROOT.rglob("*.py"):
        if ".git" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any("plana_core" in alias.name.casefold() for alias in node.names):
                    return True
            elif isinstance(node, ast.ImportFrom):
                if "plana_core" in str(node.module or "").casefold():
                    return True
    return False


def require(condition: object, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _decorated(tree: ast.AST, name: str) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            attr = decorator.func.attr if isinstance(decorator.func, ast.Attribute) else ""
            if attr != name:
                continue
            if name == "llm_tool":
                for keyword in decorator.keywords:
                    if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                        values.add(str(keyword.value.value))
            elif decorator.args and isinstance(decorator.args[0], ast.Constant):
                values.add(str(decorator.args[0].value))
    return values


def _module_values(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"READ_WORKFLOWS", "WRITE_WORKFLOWS"}:
                    values[target.id] = ast.literal_eval(node.value)
    return values


if __name__ == "__main__":
    main()
