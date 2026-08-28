from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ncqq_recovery_matcha_support import (
    REPORT_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    Case,
    MatchaAcceptanceError,
    extract_log_observations,
    hash_runtime_value,
    load_cases,
    onebot_group_event,
    render_text,
    require_acceptance_instance_alias,
    require_synthetic_id,
    sanitize_text,
    write_safe_json,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "scripts" / "fixtures" / "ncqq_recovery_matcha_cases.json"


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Prepare and audit privacy-safe NCQQ recovery tests from local artifacts.",
    )
    subparsers = command.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Generate Matcha /code scenario suites.")
    prepare.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--bot-id", default="10001")
    prepare.add_argument("--user-id", default="10002")
    prepare.add_argument("--group-id", default="10003")
    prepare.add_argument("--instance-alias")
    prepare.add_argument("--case", action="append", default=[])
    prepare.add_argument("--reply-message-id", type=int)
    prepare.add_argument("--response-timeout-ms", type=int, default=90000)
    collect = subparsers.add_parser("collect", help="Build a redacted report from test artifacts.")
    collect.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    collect.add_argument("--report", type=Path, required=True)
    collect.add_argument("--astrbot-log", type=Path, required=True)
    collect.add_argument("--matcha-run", type=Path, action="append", default=[])
    collect.add_argument("--manifest", type=Path, required=True)
    collect.add_argument("--case", action="append", default=[])
    collect.add_argument("--run-label", default="manual-matcha")
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "prepare":
            for path in prepare_suites(args):
                print(f"matcha_suite={path}")
        elif args.command == "collect":
            report = collect_report(args)
            write_safe_json(args.report.resolve(), report)
            print(f"ncqq_recovery_report={args.report.resolve()}")
            print(f"ncqq_recovery_status={report['status']}")
    except MatchaAcceptanceError as exc:
        raise SystemExit(f"ncqq_recovery_matcha_failed={exc}") from exc


def selected_cases(path: Path, selected: list[str]) -> list[Case]:
    cases = load_cases(path.resolve())
    if not selected:
        return cases
    selected_set = set(selected)
    output = [case for case in cases if case.case_id in selected_set]
    missing = sorted(selected_set - {case.case_id for case in output})
    if missing:
        raise MatchaAcceptanceError(f"unknown_cases:{','.join(missing)}")
    return output


def prepare_suites(args: argparse.Namespace) -> list[Path]:
    instance_alias = prepare_manifest_alias(
        args.manifest.resolve(), args.fixture.resolve(), args.instance_alias
    )
    bot_id = require_synthetic_id(args.bot_id, "bot_id")
    user_id = require_synthetic_id(args.user_id, "user_id")
    group_id = require_synthetic_id(args.group_id, "group_id")
    if args.response_timeout_ms < 1000 or args.response_timeout_ms > 300000:
        raise MatchaAcceptanceError("response_timeout_invalid")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for case_index, case in enumerate(selected_cases(args.fixture, args.case), start=1):
        steps: list[dict[str, Any]] = []
        for message_index, message in enumerate(case.messages, start=1):
            reply_required = bool(message.get("reply_to_previous_bot"))
            if reply_required and args.reply_message_id is None:
                steps.append(
                    {
                        "id": f"manual-anchor-{message_index}",
                        "name": "需要上一条真实机器人回复 ID，使用 --reply-message-id 重新生成",
                        "type": "delay",
                        "enabled": False,
                        "duration": 0,
                    }
                )
                continue
            text = render_text(str(message["text"]), instance_alias)
            steps.append(
                {
                    "id": f"event-{message_index}",
                    "name": f"发送自然表达 {message_index}",
                    "type": "event",
                    "enabled": True,
                    "event": onebot_group_event(
                        bot_id=bot_id,
                        user_id=user_id,
                        group_id=group_id,
                        message_id=110000 + case_index * 100 + message_index,
                        text=text,
                        reply_message_id=args.reply_message_id if reply_required else None,
                    ),
                }
            )
            if case.category == "discussion_negative":
                steps.append(
                    {
                        "id": f"negative-delay-{message_index}",
                        "name": "观察讨论负例是否错误触发工具",
                        "type": "delay",
                        "enabled": True,
                        "duration": min(args.response_timeout_ms, 15000),
                    }
                )
            else:
                steps.append(
                    {
                        "id": f"reply-{message_index}",
                        "name": f"等待机器人响应 {message_index}",
                        "type": "expect_action",
                        "enabled": True,
                        "action": "send_group_msg",
                        "timeout": args.response_timeout_ms,
                    }
                )
        suite = {
            "version": 1,
            "id": f"plana-{case.case_id}",
            "name": f"Plana NCQQ Recovery - {case.case_id}",
            "description": (
                "真实自然语言 NCQQ 恢复验收。仅使用合成 Matcha 身份；"
                "结果需结合 AstrBot 日志执行 collect，不以页面出现回复单独判定通过。"
            ),
            "steps": steps,
        }
        path = output_dir / f"{case.case_id}.matcha-scenario.json"
        path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    instance_alias = load_manifest_alias(args.manifest.resolve(), args.fixture.resolve())
    cases = selected_cases(args.fixture, args.case)
    log_text = args.astrbot_log.resolve().read_text(encoding="utf-8", errors="replace")
    observations = extract_log_observations(log_text.splitlines(), instance_alias=instance_alias)
    matcha = [summarize_matcha_run(path.resolve(), instance_alias) for path in args.matcha_run]
    results = [evaluate_case(case, observations, matcha) for case in cases]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "experiment": "ncqq_recovery_matcha",
        "run_label": sanitize_text(args.run_label),
        "generated_at_epoch": int(time.time()),
        "runtime_instance_hash": hash_runtime_value(instance_alias),
        "status": "passed" if all(item["status"] == "passed" for item in results) else "needs_review",
        "case_count": len(results),
        "observations": observations,
        "matcha_runs": matcha,
        "case_results": results,
    }


def summarize_matcha_run(path: Path, instance_alias: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict) and payload.get("suiteId"):
        candidates = [payload]
    elif isinstance(payload, dict) and payload.get("format") == "matcha.workspace":
        simulations = payload.get("data", {}).get("simulations", [])
        for item in simulations if isinstance(simulations, list) else []:
            if isinstance(item, dict) and item.get("kind") == "scenario_run":
                value = item.get("value") or item.get("data") or item.get("payload")
                if isinstance(value, dict):
                    candidates.append(value)
    safe_runs = []
    for run in candidates:
        steps = run.get("steps") if isinstance(run.get("steps"), list) else []
        safe_runs.append(
            {
                "suite": sanitize_text(str(run.get("suiteId") or run.get("suiteName") or "unknown")),
                "status": str(run.get("status") or "unknown")[:20],
                "step_statuses": [str(step.get("status") or "unknown")[:20] for step in steps if isinstance(step, dict)],
                "errors": [
                    sanitize_text(str(step.get("error") or ""), instance_alias=instance_alias)
                    for step in steps
                    if isinstance(step, dict) and step.get("error")
                ],
            }
        )
    return {"artifact": path.name, "runs": safe_runs}


def evaluate_case(
    case: Case, observations: dict[str, Any], matcha_runs: list[dict[str, Any]]
) -> dict[str, Any]:
    expected_tools = set(case.expected.get("tools") or [])
    observed_tools = set(observations["tools"])
    reasons: list[str] = []
    if expected_tools and not expected_tools.intersection(observed_tools):
        reasons.append("expected_tool_not_observed")
    if not expected_tools and any(tool in observed_tools for tool in ("ncqq_manager", "plana_service_query")):
        reasons.append("discussion_negative_triggered_tool")
    expected_delivery = str(case.expected.get("qrcode_delivery") or "none")
    if expected_delivery == "private_only" and observations["qrcode_observed"]:
        if not observations["private_delivery_observed"]:
            reasons.append("qrcode_private_delivery_not_observed")
    expected_approval = str(case.expected.get("approval") or "none")
    approval_states = set(observations["approval_states"])
    if expected_approval == "cancelled" and not approval_states.intersection({"cancelled", "rejected"}):
        reasons.append("approval_cancel_not_observed")
    if expected_approval == "confirmed" and not approval_states.intersection({"confirmed", "executing", "completed"}):
        reasons.append("approval_confirmation_not_observed")
    if not matcha_runs:
        reasons.append("matcha_run_artifact_missing")
    return {
        "case_id": case.case_id,
        "category": case.category,
        "source_hash": case.source_hash,
        "status": "passed" if not reasons else "needs_review",
        "reasons": reasons,
    }


def prepare_manifest_alias(manifest_path: Path, fixture_path: Path, requested_alias: str | None) -> str:
    if manifest_path.exists():
        alias = load_manifest_alias(manifest_path, fixture_path)
        if requested_alias is not None and require_acceptance_instance_alias(requested_alias) != alias:
            raise MatchaAcceptanceError("manifest_instance_alias_mismatch")
        return alias
    if requested_alias is None:
        raise MatchaAcceptanceError("instance_alias_required_for_new_manifest")
    alias = require_acceptance_instance_alias(requested_alias)
    payload = {
        "manifest_kind": "ncqq_recovery_matcha_run",
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "instance_alias": alias,
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return alias


def load_manifest_alias(manifest_path: Path, fixture_path: Path) -> str:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatchaAcceptanceError("run_manifest_invalid") from exc
    if payload.get("manifest_kind") != "ncqq_recovery_matcha_run":
        raise MatchaAcceptanceError("run_manifest_kind_invalid")
    if payload.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise MatchaAcceptanceError("run_manifest_schema_version_invalid")
    expected_fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    if payload.get("fixture_sha256") != expected_fixture_hash:
        raise MatchaAcceptanceError("run_manifest_fixture_mismatch")
    return require_acceptance_instance_alias(str(payload.get("instance_alias") or ""))


if __name__ == "__main__":
    main()
