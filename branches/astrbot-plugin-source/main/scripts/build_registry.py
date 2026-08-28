from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_OWNER = "memoriass"
DEFAULT_REPOSITORIES_FILE = Path(__file__).resolve().parents[1] / "repositories.json"
USER_AGENT = "memoriass-astrbot-plugin-source-builder"


def request_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_text(url: str) -> str | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def url_exists(url: str) -> bool:
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def unquote_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_metadata_yaml(text: str) -> dict[str, Any]:
    """Parse the simple top-level metadata.yaml shape used by AstrBot plugins."""
    result: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        if raw_line[:1].isspace():
            stripped = raw_line.strip()
            if current_list_key and stripped.startswith("- "):
                result.setdefault(current_list_key, []).append(
                    unquote_yaml_scalar(stripped[2:])
                )
            continue

        current_list_key = None
        if ":" not in raw_line:
            continue

        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value == "":
            result[key] = []
            current_list_key = key
        else:
            result[key] = unquote_yaml_scalar(value)

    return result


def normalize_market_key(value: str) -> str:
    value = value.strip().lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "plugin"


def load_repository_specs(path: Path, default_owner: str) -> list[dict[str, str]]:
    raw_specs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_specs, list):
        raise ValueError("repositories.json must contain a list.")

    specs: list[dict[str, str]] = []
    for item in raw_specs:
        if isinstance(item, str):
            if "/" in item:
                owner, name = item.split("/", 1)
            else:
                owner, name = default_owner, item
        elif isinstance(item, dict):
            owner = str(item.get("owner") or default_owner).strip()
            name = str(item.get("name") or item.get("repo") or "").strip()
        else:
            raise ValueError("Repository entries must be strings or objects.")

        if not owner or not name:
            raise ValueError(f"Invalid repository entry: {item!r}")
        specs.append({"owner": owner, "name": name})

    return specs


def fetch_repo(owner: str, repo_name: str) -> dict[str, Any]:
    return request_json(f"https://api.github.com/repos/{owner}/{repo_name}")


def build_registry(repo_specs: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    for spec in repo_specs:
        owner = spec["owner"]
        repo_name = spec["name"]
        repo = fetch_repo(owner, repo_name)
        if repo.get("private") or repo.get("archived"):
            continue

        branch = repo.get("default_branch") or "main"
        html_url = repo["html_url"]
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
        metadata_text = request_text(f"{raw_base}/metadata.yaml")
        if not metadata_text:
            continue

        metadata = parse_metadata_yaml(metadata_text)
        plugin_name = str(metadata.get("name") or repo_name).strip()
        desc = str(metadata.get("desc") or metadata.get("description") or "").strip()
        author = str(metadata.get("author") or owner).strip()
        version = str(metadata.get("version") or "0.0.0").strip()
        if not plugin_name or not desc or not author or not version:
            continue

        repo_url = str(metadata.get("repo") or "").strip()
        if not repo_url.startswith("https://github.com/"):
            repo_url = html_url

        entry: dict[str, Any] = {
            "name": plugin_name,
            "display_name": str(metadata.get("display_name") or "").strip(),
            "desc": desc,
            "short_desc": str(metadata.get("short_desc") or "").strip(),
            "author": author,
            "repo": repo_url,
            "tags": metadata.get("tags") if isinstance(metadata.get("tags"), list) else [],
            "version": version,
            "updated_at": str(repo.get("updated_at") or ""),
            "download_url": f"{html_url}/archive/refs/heads/{branch}.zip",
        }

        support_platforms = metadata.get("support_platforms")
        if isinstance(support_platforms, list):
            entry["support_platforms"] = support_platforms

        astrbot_version = str(metadata.get("astrbot_version") or "").strip()
        if astrbot_version:
            entry["astrbot_version"] = astrbot_version

        logo_url = f"{raw_base}/logo.png"
        if url_exists(logo_url):
            entry["logo"] = logo_url

        entry = {key: value for key, value in entry.items() if value not in ("", [], None)}
        registry[normalize_market_key(plugin_name)] = entry

    return registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument(
        "--repositories",
        default=str(DEFAULT_REPOSITORIES_FILE),
        help="Path to the fixed repository allowlist.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1]),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    repo_specs = load_repository_specs(Path(args.repositories).resolve(), args.owner)
    registry = build_registry(repo_specs)
    if not registry:
        print("No AstrBot plugin repositories were found.", file=sys.stderr)
        return 1

    plugin_json = json.dumps(registry, ensure_ascii=False, indent=2)
    plugin_json += "\n"
    md5 = hashlib.md5(plugin_json.encode("utf-8")).hexdigest()
    md5_json = json.dumps(
        {
            "md5": md5,
            "count": len(registry),
        },
        ensure_ascii=False,
        indent=2,
    )
    md5_json += "\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "plugins.json").write_text(plugin_json, encoding="utf-8")
    (output_dir / "plugins-md5.json").write_text(md5_json, encoding="utf-8")

    print(f"Generated {len(registry)} plugin entries.")
    print(f"MD5: {md5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
