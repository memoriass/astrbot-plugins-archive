from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "compatibility-manifest.json"
RETAINED_PLUGIN_IDS = {
    "astrbot_plugin_plana_core",
    "astrbot_plugin_plana_memory_warehouse",
    "astrbot_plugin_plana_bridge_gateway",
    "astrbot_plugin_plana_gallery",
    "astrbot_plugin_ncqq_manager",
    "astrbot_plugin_ani_rss",
    "astrbot_plugin_komga_manager",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def parse_simple_yaml(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw[:1].isspace() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def git_output(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    require(completed.returncode == 0, f"git_failed={repo.name}:{' '.join(args)}")
    return completed.stdout.strip()


def repository_text(repo: Path) -> str:
    chunks: list[str] = []
    for path in repo.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in {".py", ".md", ".json", ".yaml", ".yml"}:
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def validate_plugin(ecosystem_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    plugin_id = str(entry["id"])
    repo = ecosystem_root / str(entry["path"])
    require(repo.is_dir(), f"plugin_directory_missing={plugin_id}:{repo}")
    metadata_path = repo / "metadata.yaml"
    require(metadata_path.is_file(), f"metadata_missing={plugin_id}")
    metadata = parse_simple_yaml(metadata_path)
    expected_metadata_name = str(entry.get("metadata_name") or plugin_id)
    require(
        metadata.get("name") == expected_metadata_name,
        f"metadata_name_mismatch={plugin_id}:{metadata.get('name')}",
    )
    require(
        metadata.get("version") == str(entry["version"]),
        f"metadata_version_mismatch={plugin_id}:{metadata.get('version')}",
    )
    manifest_astrbot = str(entry.get("astrbot_version") or "")
    expected_astrbot = manifest_astrbot or ">=4.25.0,<5.0.0"
    require(
        metadata.get("astrbot_version") == expected_astrbot,
        f"astrbot_version_mismatch={plugin_id}:{metadata.get('astrbot_version')}",
    )

    git_dir = repo / ".git"
    git_required = bool(entry.get("git_required", True))
    if git_required:
        require(git_dir.exists(), f"git_repository_missing={plugin_id}")
        head = git_output(repo, "rev-parse", "HEAD")
        baseline = str(entry.get("baseline_commit") or "")
        baseline_check = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", baseline, head],
            check=False,
            capture_output=True,
        )
        require(
            bool(baseline) and baseline_check.returncode == 0,
            f"baseline_commit_drift={plugin_id}:baseline={baseline}:head={head}",
        )
        branch = git_output(repo, "branch", "--show-current")
        dirty = bool(git_output(repo, "status", "--short"))
    else:
        head = ""
        branch = ""
        dirty = True

    contracts = [str(item) for item in entry.get("contracts", [])]
    if contracts:
        text = repository_text(repo)
        missing_contracts = [item for item in contracts if item not in text]
        require(not missing_contracts, f"contracts_missing={plugin_id}:{missing_contracts}")

    checks = entry.get("checks")
    require(isinstance(checks, list) and checks, f"checks_missing={plugin_id}")
    for command in checks:
        require(
            isinstance(command, str) and command.startswith("python scripts/"),
            f"unsafe_check_command={plugin_id}:{command!r}",
        )
        script = shlex.split(command, posix=False)[1].replace("/", str(Path("/")).replace("/", "\\"))
        require((repo / script).is_file(), f"check_script_missing={plugin_id}:{script}")
    benchmark_checks = entry.get("benchmark_checks", [])
    require(isinstance(benchmark_checks, list), f"benchmark_checks_invalid={plugin_id}")
    for command in benchmark_checks:
        require(
            isinstance(command, str) and command.startswith("python scripts/"),
            f"unsafe_benchmark_command={plugin_id}:{command!r}",
        )
        script = shlex.split(command, posix=False)[1].replace("/", "\\")
        require((repo / script).is_file(), f"benchmark_script_missing={plugin_id}:{script}")

    return {
        "id": plugin_id,
        "version": metadata["version"],
        "branch": branch,
        "head": head,
        "dirty": dirty,
        "release_blocker": str(entry.get("release_blocker") or ""),
    }


def run_checks(
    ecosystem_root: Path,
    plugins: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for entry in plugins:
        repo = ecosystem_root / str(entry["path"])
        for command in [*entry["checks"], *entry.get("benchmark_checks", [])]:
            args = shlex.split(str(command), posix=False)
            completed = subprocess.run(args, cwd=repo, check=False)
            if completed.returncode != 0:
                failures.append(
                    {
                        "id": str(entry["id"]),
                        "command": str(command),
                        "returncode": completed.returncode,
                    }
                )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ecosystem-root",
        type=Path,
        default=ROOT.parent,
        help="Directory containing the Plana plugin repositories.",
    )
    parser.add_argument("--run-checks", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    require(
        manifest.get("schema_version") == "plana.ecosystem.compatibility.v1",
        "manifest_schema_version_invalid",
    )
    plugins = manifest.get("plugins")
    require(isinstance(plugins, list), "manifest_plugins_invalid")
    ids = [str(item.get("id") or "") for item in plugins]
    require(len(ids) == len(set(ids)), "manifest_plugin_ids_not_unique")
    require(set(ids) == RETAINED_PLUGIN_IDS, f"manifest_plugin_set_invalid={ids}")

    results = [validate_plugin(args.ecosystem_root.resolve(), item) for item in plugins]
    check_failures = (
        run_checks(args.ecosystem_root.resolve(), plugins)
        if args.run_checks
        else []
    )

    blockers = [item for item in results if item["release_blocker"]]
    dirty = [item["id"] for item in results if item["dirty"]]
    print(
        json.dumps(
            {
                "ok": not check_failures,
                "schema_version": manifest["schema_version"],
                "release_ready": bool(manifest.get("release_ready", False)),
                "plugin_count": len(results),
                "dirty_plugins": dirty,
                "release_blockers": [item["id"] for item in blockers],
                "checks_run": bool(args.run_checks),
                "check_failures": check_failures,
            },
            ensure_ascii=False,
        )
    )
    if check_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
