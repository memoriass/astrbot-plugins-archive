from __future__ import annotations

import argparse
import ast
import re
import subprocess
from pathlib import Path


REPOSITORIES = (
    "astrbot_plugin_plana_core",
    "astrbot_plugin_plana_bridge_gateway",
    "astrbot_plugin_plana_gallery",
    "astrbot_plugin_plana_memory_warehouse",
    "astrbot_plugin_ncqq_manager",
    "astrbot_plugin_ani_rss",
    "astrbot_plugin_komga_manager",
)
REQUIRED_FILES = ("main.py", "metadata.yaml", "_conf_schema.json", "README.md")
HOST_MODULES = {"astrbot", "quart"}
DEPENDENCY_NAMES = {
    "aiohttp": "aiohttp",
    "jieba": "jieba",
    "PIL": "pillow",
    "pylitehtml": "pylitehtml",
}
OPTIONAL_MODULES = {"playwright"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def tracked_python(repository: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repository / item for item in result.stdout.splitlines() if item]


def production_python(repository: Path) -> list[Path]:
    return [
        path
        for path in tracked_python(repository)
        if path.is_file()
        if not path.relative_to(repository).parts[0] in {"scripts", "tests"}
    ]


def metadata_value(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text)
    return match.group(1).strip() if match else ""


def requirement_names(repository: Path) -> set[str]:
    path = repository / "requirements.txt"
    if not path.exists():
        return set()
    names = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        clean = raw.split("#", 1)[0].strip()
        if not clean:
            continue
        names.add(re.split(r"[<>=!~\[]", clean, maxsplit=1)[0].strip().casefold())
    return names


def imported_roots(paths: list[Path]) -> set[str]:
    roots = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


def decorated_module_handlers(main_path: Path) -> list[str]:
    tree = ast.parse(main_path.read_text(encoding="utf-8-sig"), filename=str(main_path))
    names = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if "filter." in ast.unparse(decorator):
                names.append(node.name)
                break
    return names


def local_module_names(repository: Path) -> set[str]:
    names = {path.stem for path in repository.glob("*.py")}
    names.update(path.name for path in repository.iterdir() if path.is_dir())
    return names


def check_repository(repository: Path) -> list[str]:
    missing = [name for name in REQUIRED_FILES if not (repository / name).is_file()]
    require(not missing, f"astrbot_compliance_missing_files={repository.name}:{missing}")
    metadata = (repository / "metadata.yaml").read_text(encoding="utf-8-sig")
    for key in ("name", "version", "repo", "astrbot_version"):
        require(metadata_value(metadata, key), f"astrbot_metadata_missing={repository.name}:{key}")
    main_path = repository / "main.py"
    main_tree = ast.parse(main_path.read_text(encoding="utf-8-sig"), filename=str(main_path))
    classes = [node.name for node in main_tree.body if isinstance(node, ast.ClassDef)]
    require(classes, f"astrbot_main_plugin_class_missing={repository.name}")
    module_handlers = decorated_module_handlers(main_path)
    require(
        not module_handlers,
        f"astrbot_module_level_handlers={repository.name}:{module_handlers}",
    )
    paths = production_python(repository)
    source = "\n".join(path.read_text(encoding="utf-8-sig") for path in paths)
    require(
        "super().__init__(context)" in source,
        f"astrbot_star_super_init_missing={repository.name}",
    )
    require(
        not re.search(r"(?m)^\s*(?:from\s+requests\s+import|import\s+requests\b)", source),
        f"astrbot_blocking_requests_import={repository.name}",
    )
    imports = imported_roots(paths)
    local = local_module_names(repository)
    requirements = requirement_names(repository)
    missing_dependencies = []
    for module, package in DEPENDENCY_NAMES.items():
        if module in imports and module not in HOST_MODULES | local:
            if package.casefold() not in requirements:
                missing_dependencies.append(package)
    require(
        not missing_dependencies,
        f"astrbot_requirements_missing={repository.name}:{sorted(missing_dependencies)}",
    )
    optional = sorted(module for module in OPTIONAL_MODULES if module in imports)
    warnings = []
    declared_license = metadata_value(metadata, "license")
    if declared_license and not any(repository.glob("LICENSE*")):
        warnings.append(f"declared_license_without_file:{declared_license}")
    if optional:
        warnings.append("optional_dependencies:" + ",".join(optional))
    print(
        f"astrbot_plugin_compliance=ok:repo={repository.name}:"
        f"classes={','.join(classes)}:warnings={';'.join(warnings) or 'none'}"
    )
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Check retained Plana AstrBot plugins.")
    parser.add_argument(
        "--git-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    args = parser.parse_args()
    git_root = args.git_root.resolve()
    missing = [name for name in REPOSITORIES if not (git_root / name).is_dir()]
    require(not missing, f"astrbot_family_repositories_missing={missing}")
    warnings = {}
    for name in REPOSITORIES:
        repository_warnings = check_repository(git_root / name)
        if repository_warnings:
            warnings[name] = repository_warnings
    print(f"astrbot_plugin_family_compliance=ok:repos={len(REPOSITORIES)}:warnings={warnings}")


if __name__ == "__main__":
    main()
