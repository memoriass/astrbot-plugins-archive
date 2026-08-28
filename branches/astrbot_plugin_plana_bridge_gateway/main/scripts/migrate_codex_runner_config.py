from __future__ import annotations

import argparse
import json
from pathlib import Path


MAPPING = {
    "enable_hermes_runner": "enable_codex_runner",
    "hermes_runner_url": "codex_runner_url",
    "hermes_runner_token": "codex_runner_token",
    "hermes_runner_id": "codex_runner_id",
    "hermes_runner_lanes": "codex_runner_lanes",
    "hermes_runner_timeout_seconds": "codex_runner_timeout_seconds",
    "hermes_runner_submit_timeout_seconds": "codex_runner_submit_timeout_seconds",
    "hermes_runner_delivery_concurrency": "codex_runner_delivery_concurrency",
    "hermes_result_callback_url": "codex_result_callback_url",
}


def migrate(data: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    migrated = dict(data)
    changed: list[str] = []
    for old_key, new_key in MAPPING.items():
        if old_key not in migrated:
            continue
        if new_key not in migrated:
            migrated[new_key] = migrated[old_key]
        migrated.pop(old_key, None)
        changed.append(f"{old_key}->{new_key}")
    if "hermes_runner_protocol_version" in migrated:
        migrated.pop("hermes_runner_protocol_version", None)
        changed.append("hermes_runner_protocol_version->codex_runner_protocol_version")
    migrated["codex_runner_protocol_version"] = "plana.codex.runner.v1"
    return migrated, changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Bridge Runner config to Codex names.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise SystemExit("bridge_config_must_be_object")
    migrated, changed = migrate(data)
    if args.write:
        args.path.write_text(
            json.dumps(migrated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"codex_config_migration={'written' if args.write else 'preview'}:changes={len(changed)}")
    for item in changed:
        print(item)


if __name__ == "__main__":
    main()
