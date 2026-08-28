from __future__ import annotations

import json
import tempfile
from argparse import Namespace
from pathlib import Path

from ncqq_recovery_matcha_support import (
    MatchaAcceptanceError,
    assert_privacy_safe,
    hash_runtime_value,
    load_cases,
    require_acceptance_instance_alias,
)
from run_ncqq_recovery_matcha import DEFAULT_FIXTURE, collect_report, parser, prepare_suites


VALID_ALIAS = "accept-ncqq-20260719-7f3a9c2d"


def require_rejected_alias(alias: str, expected_error: str) -> None:
    try:
        require_acceptance_instance_alias(alias)
    except MatchaAcceptanceError as exc:
        if str(exc) != expected_error:
            raise SystemExit(f"ncqq_matcha_alias_wrong_error={alias}:{exc}") from exc
    else:
        raise SystemExit(f"ncqq_matcha_alias_not_rejected={alias}")


def main() -> None:
    cases = load_cases(DEFAULT_FIXTURE)
    categories = {case.category for case in cases}
    required = {
        "discussion_negative",
        "write_cancel",
        "write_confirm",
        "context_pronoun",
        "ambiguity",
        "reply_anchor",
    }
    if not required.issubset(categories):
        raise SystemExit(f"ncqq_matcha_categories_missing={sorted(required - categories)}")
    for forbidden in ("arona", "plana", "codex-qr-test-07120029"):
        require_rejected_alias(forbidden, f"instance_alias_forbidden:{forbidden}")
    for invalid in (
        "matcha-acceptance",
        "accept-ncqq-20260719-test",
        "accept-ncqq-20260230-7f3a9c2d",
    ):
        expected = (
            "instance_alias_date_invalid"
            if invalid == "accept-ncqq-20260230-7f3a9c2d"
            else "instance_alias_must_match_accept_ncqq_date_suffix"
        )
        require_rejected_alias(invalid, expected)
    command_action = next(action for action in parser()._actions if action.dest == "command")
    if set(command_action.choices) != {"prepare", "collect"}:
        raise SystemExit("ncqq_matcha_command_boundary_invalid")
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        manifest = temporary_path / "run-manifest.json"
        paths = prepare_suites(
            Namespace(
                fixture=DEFAULT_FIXTURE,
                output_dir=temporary_path / "first",
                manifest=manifest,
                bot_id="10001",
                user_id="10002",
                group_id="10003",
                instance_alias=VALID_ALIAS,
                case=[],
                reply_message_id=11001,
                response_timeout_ms=1000,
            )
        )
        if len(paths) != len(cases):
            raise SystemExit("ncqq_matcha_suite_count_invalid")
        for path in paths:
            suite = json.loads(path.read_text(encoding="utf-8"))
            if suite.get("version") != 1 or not suite.get("steps"):
                raise SystemExit(f"ncqq_matcha_suite_invalid={path.name}")
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        if manifest_payload.get("instance_alias") != VALID_ALIAS:
            raise SystemExit("ncqq_matcha_manifest_alias_invalid")
        repeated_paths = prepare_suites(
            Namespace(
                fixture=DEFAULT_FIXTURE,
                output_dir=temporary_path / "second",
                manifest=manifest,
                bot_id="10001",
                user_id="10002",
                group_id="10003",
                instance_alias=None,
                case=[],
                reply_message_id=11001,
                response_timeout_ms=1000,
            )
        )
        first_bytes = {path.name: path.read_bytes() for path in paths}
        repeated_bytes = {path.name: path.read_bytes() for path in repeated_paths}
        if first_bytes != repeated_bytes:
            raise SystemExit("ncqq_matcha_suite_generation_not_deterministic")
        local_log = temporary_path / "astrbot.log"
        local_log.write_text("", encoding="utf-8")
        report = collect_report(
            Namespace(
                fixture=DEFAULT_FIXTURE,
                report=temporary_path / "report.json",
                astrbot_log=local_log,
                matcha_run=[],
                manifest=manifest,
                case=[],
                run_label="deterministic-check",
            )
        )
        if report.get("runtime_instance_hash") != hash_runtime_value(VALID_ALIAS):
            raise SystemExit("ncqq_matcha_collect_manifest_alias_invalid")
        try:
            prepare_suites(
                Namespace(
                    fixture=DEFAULT_FIXTURE,
                    output_dir=temporary_path / "mismatch",
                    manifest=manifest,
                    bot_id="10001",
                    user_id="10002",
                    group_id="10003",
                    instance_alias="accept-ncqq-20260719-8e4b0d3c",
                    case=[],
                    reply_message_id=11001,
                    response_timeout_ms=1000,
                )
            )
        except MatchaAcceptanceError as exc:
            if str(exc) != "manifest_instance_alias_mismatch":
                raise SystemExit(f"ncqq_matcha_manifest_mismatch_wrong_error={exc}") from exc
        else:
            raise SystemExit("ncqq_matcha_manifest_alias_mismatch_not_rejected")
    sample_report = {
        "schema_version": 1,
        "experiment": "ncqq_recovery_matcha",
        "runtime_instance_hash": "a" * 64,
        "status": "needs_review",
        "case_results": [{"case_id": cases[0].case_id, "status": "needs_review"}],
    }
    assert_privacy_safe(sample_report)
    print(f"ncqq_recovery_matcha_check=ok:cases={len(cases)}:categories={len(categories)}")


if __name__ == "__main__":
    main()
