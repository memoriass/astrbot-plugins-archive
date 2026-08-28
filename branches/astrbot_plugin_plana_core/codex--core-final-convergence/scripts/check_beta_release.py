from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_METADATA = {
    "name": "astrbot_plugin_plana_core",
    "display_name": "Plana Core",
    "author": None,
    "desc": None,
    "short_desc": None,
    "version": None,
    "repo": None,
    "license": "AGPL-3.0-or-later",
}

REQUIRED_FILES = [
    "metadata.yaml",
    "_conf_schema.json",
    "README.md",
    "ARCHITECTURE.md",
    "web/dashboard_shell.md",
    "pages/dashboard/index.html",
    "memory/memory_kernel.md",
    "scripts/check_final_convergence.py",
    "scripts/archive_retired_state.py",
    "scripts/check_ecosystem_compatibility.py",
    "compatibility-manifest.json",
    "logo.png",
    ".gitignore",
]

REQUIRED_GITIGNORE = [
    "__pycache__/",
    "*.sqlite3",
    "*.sqlite3-wal",
    "*.log",
    "*_config.json",
    ".env",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    "dist/",
    "data/",
    "backups/",
    "tmp/",
]

README_REQUIRED = [
    "Memory Warehouse",
    "领域插件",
    "Codex Runner",
    "astrbot_plugin_plana_bridge_gateway",
    "astrbot_plugin_plana_memory_warehouse",
    "check_bridge_gateway.py",
    "check_memory_warehouse_plugin.py",
    "check_code_acceptance.py --tier code",
    "archive_retired_state.py",
]

README_FORBIDDEN = [
    "顶部 topbar",
    "检索实验室",
    "工作流风险复盘",
    "技能中心治理状态",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def parse_simple_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    current_list: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1].isspace():
            stripped = raw.strip()
            if current_list and stripped.startswith("- "):
                result.setdefault(current_list, []).append(stripped[2:].strip().strip('"'))
            continue
        current_list = None
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            result[key] = []
            current_list = key
        else:
            result[key] = value.strip('"')
    return result


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), "logo_not_png")
    require(data[12:16] == b"IHDR", "logo_missing_ihdr")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    missing_files = [item for item in REQUIRED_FILES if not (ROOT / item).exists()]
    require(not missing_files, f"release_files_missing={missing_files}")

    metadata = parse_simple_yaml(ROOT / "metadata.yaml")
    missing_metadata = [key for key in REQUIRED_METADATA if key not in metadata]
    require(not missing_metadata, f"metadata_missing={missing_metadata}")
    for key, expected in REQUIRED_METADATA.items():
        if expected is not None:
            require(metadata.get(key) == expected, f"metadata_{key}_unexpected={metadata.get(key)!r}")
        else:
            require(bool(str(metadata.get(key) or "").strip()), f"metadata_{key}_empty")

    version = str(metadata["version"])
    require(re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", version) is not None, f"metadata_version_invalid={version}")
    require("beta" in version, f"metadata_version_not_beta={version}")
    require(str(metadata["repo"]).startswith("https://github.com/"), "metadata_repo_not_github")

    tags = metadata.get("tags")
    require(isinstance(tags, list) and {"memory", "companion", "web", "codex"}.issubset(set(tags)), "metadata_tags_incomplete")
    platforms = metadata.get("support_platforms")
    require(isinstance(platforms, list) and platforms, "metadata_support_platforms_empty")

    json.load((ROOT / "_conf_schema.json").open(encoding="utf-8"))

    width, height = png_size(ROOT / "logo.png")
    require((width, height) == (512, 512), f"logo_size_unexpected={width}x{height}")
    require((ROOT / "logo.png").stat().st_size <= 512 * 1024, "logo_too_large")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    missing_gitignore = [item for item in REQUIRED_GITIGNORE if item not in gitignore]
    require(not missing_gitignore, f"gitignore_missing={missing_gitignore}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing_readme = [item for item in README_REQUIRED if item not in readme]
    require(not missing_readme, f"readme_missing={missing_readme}")
    forbidden_readme = [item for item in README_FORBIDDEN if item in readme]
    require(not forbidden_readme, f"readme_forbidden={forbidden_readme}")

    acceptance = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_code_acceptance.py"), "--tier", "code"],
        cwd=ROOT,
        check=False,
    )
    require(acceptance.returncode == 0, f"code_acceptance_failed={acceptance.returncode}")
    print("beta_release_check=ok")


if __name__ == "__main__":
    main()
