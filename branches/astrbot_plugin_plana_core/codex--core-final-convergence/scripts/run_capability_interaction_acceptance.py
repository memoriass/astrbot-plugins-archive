from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_plana_core.service_gateway import ServiceGatewayClient, ServiceGatewayError

from capability_interaction_support import (
    REPORT_SCHEMA_VERSION,
    STAGES,
    AcceptanceError,
    acceptance_service_ref,
    compare_arguments,
    expected_arguments,
    fixture_digest,
    load_cases,
    load_jsonl,
    load_sandbox,
    repository_commit,
    report_status,
    resolve_sandbox,
    safe_error,
    safe_identifier,
    safe_optional_identifier,
    write_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run privacy-safe Plana capability interaction acceptance.",
        epilog=(
            "model-shadow requires JSONL rows with case_id, attempt (1..3), "
            "proposed_capability, arguments, provider, and model. It validates recorded "
            "AstrBot traces and never pretends to call a local provider."
        ),
    )
    parser.add_argument("--stage", required=True, choices=sorted(STAGES))
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--trace-jsonl", type=Path, help="Required for model-shadow.")
    parser.add_argument("--sandbox-config", type=Path, help="JSON values for $sandbox.* and cleanup.")
    parser.add_argument("--gateway-url", default=os.getenv("PLANA_ACCEPTANCE_GATEWAY_URL", ""))
    parser.add_argument("--gateway-token", default=os.getenv("PLANA_ACCEPTANCE_GATEWAY_TOKEN", ""))
    parser.add_argument("--provider", default="", help="Expected provider identifier; never a credential.")
    parser.add_argument("--model", default="", help="Expected model identifier.")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        report = asyncio.run(_run(args))
        write_report(args.report.resolve(), report)
    except AcceptanceError as exc:
        raise SystemExit(f"capability_interaction_acceptance_failed={exc}") from exc
    print(f"capability_interaction_report={args.report.resolve()}")
    print(f"capability_interaction_status={report['status']}")
    if report["status"] != "passed":
        raise SystemExit(1)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    fixture_path = args.fixture.resolve()
    sandbox = load_sandbox(args.sandbox_config.resolve() if args.sandbox_config else None)
    cases = load_cases(fixture_path, args.stage)
    provider = safe_optional_identifier(args.provider, "provider")
    model = safe_optional_identifier(args.model, "model")
    if args.stage == "model-shadow":
        if args.trace_jsonl is None:
            raise AcceptanceError("model_shadow_trace_jsonl_required")
        results, trace_provider, trace_model = _run_model_shadow(
            cases, load_jsonl(args.trace_jsonl.resolve()), sandbox, provider, model,
        )
        provider = provider or trace_provider
        model = model or trace_model
    else:
        if not args.gateway_url or not args.gateway_token:
            raise AcceptanceError("live_gateway_configuration_required")
        client = ServiceGatewayClient(
            base_url=args.gateway_url,
            token=args.gateway_token,
            timeout_seconds=args.timeout_seconds,
        )
        results = []
        for case in cases:
            if args.stage == "read-live":
                results.append(await _run_read_live(client, case.case_id, case.payload, sandbox))
            else:
                results.append(await _run_write_sandbox(client, case.case_id, case.payload, sandbox))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "commit": repository_commit(ROOT),
        "fixture_sha256": fixture_digest(fixture_path),
        "provider": provider or "not_applicable",
        "model": model or "not_applicable",
        "stage": args.stage,
        "status": report_status(results),
        "case_count": len(results),
        "case_results": results,
    }


def _run_model_shadow(
    cases: list[Any],
    rows: list[dict[str, Any]],
    sandbox: dict[str, Any],
    expected_provider: str,
    expected_model: str,
) -> tuple[list[dict[str, Any]], str, str]:
    by_case: dict[str, list[dict[str, Any]]] = {}
    providers: set[str] = set()
    models: set[str] = set()
    for row in rows:
        case_id = safe_identifier(row.get("case_id"), "trace_case_id")
        by_case.setdefault(case_id, []).append(row)
        providers.add(safe_identifier(row.get("provider"), "trace_provider"))
        models.add(safe_identifier(row.get("model"), "trace_model"))
    if len(providers) != 1 or len(models) != 1:
        raise AcceptanceError("trace_provider_model_must_be_stable")
    provider = next(iter(providers))
    model = next(iter(models))
    if expected_provider and provider != expected_provider:
        raise AcceptanceError("trace_provider_mismatch")
    if expected_model and model != expected_model:
        raise AcceptanceError("trace_model_mismatch")
    results = [
        _evaluate_shadow_case(case.case_id, case.payload, by_case.get(case.case_id, []), sandbox)
        for case in cases
    ]
    return results, provider, model


def _evaluate_shadow_case(
    case_id: str,
    case: dict[str, Any],
    rows: list[dict[str, Any]],
    sandbox: dict[str, Any],
) -> dict[str, Any]:
    expected = case.get("expected_capability")
    if expected is not None:
        expected = safe_identifier(expected, "expected_capability")
    forbidden = {
        safe_identifier(item, "forbidden_capability")
        for item in case.get("forbidden_capabilities", [])
    }
    expected_args = expected_arguments(case, sandbox)
    allowed = {
        safe_identifier(item, "allowed_capability")
        for item in case.get("allowed_capabilities", [])
    }
    attempts: list[dict[str, Any]] = []
    seen_attempts: set[int] = set()
    passed_count = 0
    forbidden_hit = False
    for row in sorted(rows, key=lambda item: int(item.get("attempt") or 0)):
        attempt = int(row.get("attempt") or 0)
        if attempt not in {1, 2, 3} or attempt in seen_attempts:
            raise AcceptanceError(f"trace_attempt_invalid:{case_id}")
        seen_attempts.add(attempt)
        raw_calls = row.get("tool_calls")
        if raw_calls is None:
            raw_calls = [{
                "capability": row.get("proposed_capability"),
                "arguments": row.get("arguments") or {},
            }] if row.get("proposed_capability") else []
        if not isinstance(raw_calls, list) or any(not isinstance(item, dict) for item in raw_calls):
            raise AcceptanceError(f"trace_tool_calls_invalid:{case_id}")
        calls = []
        for item in raw_calls:
            capability = safe_identifier(item.get("capability"), "proposed_capability")
            calls.append((capability, item.get("arguments") or {}))
        proposed = [capability for capability, _arguments in calls]
        expected_call = next((item for item in calls if item[0] == expected), None)
        if expected is None:
            argument_ok, differing, extra = (True, [], [])
            capability_ok = not calls
        elif expected_call is None:
            argument_ok, differing, extra = (False, sorted(expected_args), [])
            capability_ok = False
        else:
            argument_ok, differing, extra = compare_arguments(
                expected_call[1], expected_args, str(case.get("argument_match") or "subset"),
            )
            capability_ok = True
        hit_capabilities = sorted(set(proposed) & forbidden)
        unexpected = sorted(
            capability for capability in set(proposed)
            if capability not in allowed
        ) if allowed else ([] if expected is not None else sorted(set(proposed)))
        hit = bool(hit_capabilities)
        passed = capability_ok and argument_ok and not hit and not unexpected
        passed_count += int(passed)
        forbidden_hit = forbidden_hit or hit
        attempts.append({
            "attempt": attempt,
            "proposed_capabilities": proposed,
            "capability_match": capability_ok,
            "argument_match": argument_ok,
            "differing_argument_keys": differing,
            "extra_argument_keys": extra,
            "forbidden_hit": hit,
            "forbidden_capabilities": hit_capabilities,
            "unexpected_capabilities": unexpected,
            "status": "passed" if passed else "failed",
        })
    complete = seen_attempts == {1, 2, 3}
    status = "passed" if complete and passed_count >= 2 and not forbidden_hit else "failed"
    return {
        "case_id": case_id,
        "expected_capability": expected,
        "attempts_complete": complete,
        "majority_passed": passed_count >= 2,
        "forbidden_hit": forbidden_hit,
        "status": status,
        "attempts": attempts,
    }


async def _run_read_live(
    client: ServiceGatewayClient,
    case_id: str,
    case: dict[str, Any],
    sandbox: dict[str, Any],
) -> dict[str, Any]:
    capability = safe_identifier(case.get("expected_capability"), "expected_capability")
    service_ref = acceptance_service_ref(case, capability)
    resource_id = str(resolve_sandbox(case.get("resource_id") or "default", sandbox))
    arguments = expected_arguments(case, sandbox)
    try:
        response = await client.query(
            request_id=f"acceptance-{uuid.uuid4().hex}",
            service_ref=service_ref,
            capability=capability,
            resource_id=resource_id,
            arguments=arguments,
        )
        missing = _missing_response_keys(response, case.get("expected_response_keys") or [])
        response_kind = _response_kind(response)
        status = "passed" if _gateway_result_passed(response) and not missing else "failed"
        return {
            "case_id": case_id,
            "capability": capability,
            "service_ref": service_ref,
            "response_kind": response_kind,
            "missing_response_keys": missing,
            "status": status,
        }
    except (ServiceGatewayError, AcceptanceError) as exc:
        return {
            "case_id": case_id,
            "capability": capability,
            "service_ref": service_ref,
            "response_kind": "error",
            "error": safe_error(exc),
            "status": "failed",
        }


async def _run_write_sandbox(
    client: ServiceGatewayClient,
    case_id: str,
    case: dict[str, Any],
    sandbox: dict[str, Any],
) -> dict[str, Any]:
    capability = safe_identifier(case.get("expected_capability"), "expected_capability")
    service_ref = acceptance_service_ref(case, capability)
    resource_id = str(resolve_sandbox(case.get("resource_id") or "default", sandbox))
    arguments = expected_arguments(case, sandbox)
    cleanup_map = sandbox.get("cleanup") if isinstance(sandbox.get("cleanup"), dict) else {}
    cleanup = case.get("cleanup") or cleanup_map.get(case_id)
    if not isinstance(cleanup, dict):
        raise AcceptanceError(f"cleanup_configuration_required:{case_id}")
    confirmation_rejected = False
    execute_status = "not_run"
    cleanup_status = "not_run"
    error = ""
    try:
        await client.execute(
            request_id=f"acceptance-unconfirmed-{uuid.uuid4().hex}",
            service_ref=service_ref,
            capability=capability,
            resource_id=resource_id,
            arguments=arguments,
            confirmed=False,
        )
    except ServiceGatewayError as exc:
        confirmation_rejected = str(exc) == "service_execution_confirmation_required"
    if confirmation_rejected:
        try:
            response = await client.execute(
                request_id=f"acceptance-confirmed-{uuid.uuid4().hex}",
                service_ref=service_ref,
                capability=capability,
                resource_id=resource_id,
                arguments=arguments,
                confirmed=True,
            )
            execute_status = "passed" if _gateway_result_passed(response) else "failed"
        except ServiceGatewayError as exc:
            execute_status = "failed"
            error = safe_error(exc)
    if execute_status == "passed":
        try:
            cleanup_capability = safe_identifier(cleanup.get("capability"), "cleanup_capability")
            cleanup_case = dict(case)
            cleanup_case["service_ref"] = cleanup.get("service_ref") or case.get("service_ref")
            cleanup_ref = acceptance_service_ref(cleanup_case, cleanup_capability)
            cleanup_resource = str(resolve_sandbox(cleanup.get("resource_id") or resource_id, sandbox))
            cleanup_arguments = resolve_sandbox(cleanup.get("arguments") or {}, sandbox)
            if not isinstance(cleanup_arguments, dict):
                raise AcceptanceError("cleanup_arguments_invalid")
            cleanup_response = await client.execute(
                request_id=f"acceptance-cleanup-{uuid.uuid4().hex}",
                service_ref=cleanup_ref,
                capability=cleanup_capability,
                resource_id=cleanup_resource,
                arguments=cleanup_arguments,
                confirmed=True,
            )
            cleanup_status = "passed" if _gateway_result_passed(cleanup_response) else "failed"
        except (ServiceGatewayError, AcceptanceError) as exc:
            cleanup_status = "failed"
            error = error or safe_error(exc)
    passed = confirmation_rejected and execute_status == "passed" and cleanup_status == "passed"
    result = {
        "case_id": case_id,
        "capability": capability,
        "service_ref": service_ref,
        "unconfirmed_rejected": confirmation_rejected,
        "execute_status": execute_status,
        "cleanup_configured": True,
        "cleanup_status": cleanup_status,
        "status": "passed" if passed else "failed",
    }
    if error:
        result["error"] = error
    return result


def _missing_response_keys(response: Any, keys: Any) -> list[str]:
    if not isinstance(keys, list):
        raise AcceptanceError("expected_response_keys_invalid")
    if not isinstance(response, dict):
        return [str(item) for item in keys]
    return sorted(str(item) for item in keys if str(item) not in response)


def _response_kind(response: Any) -> str:
    if not isinstance(response, dict):
        return "invalid"
    status = str(response.get("status") or "success").strip().lower()
    allowed = {"success", "succeeded", "completed", "degraded", "empty"}
    return status if status in allowed else "object"


def _gateway_result_passed(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    status = str(response.get("status") or "success").strip().lower()
    return status not in {"error", "failed", "rejected", "blocked", "cancelled"}


if __name__ == "__main__":
    main()
