from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


HASH_NAMESPACE = "plana-route-replay-v1"
MESSAGE_RE = re.compile(r"WebChatAdapter: .*?text=(?P<quote>['\"])(?P<text>.*)(?P=quote)\)\]")
ROUTE_RE = re.compile(r"Plana turn route: .*?profile=(?P<profile>[a-z_]+)")
TOOL_RE = re.compile(r"使用工具：plana_service_query，参数：(?P<arguments>\{.*\})")
RESULT_RE = re.compile(r"Tool `plana_service_query` Result: (?P<result>\{.*\})")
MODEL_RE = re.compile(r"\bmodel=['\"](?P<model>[^'\"]+)['\"]")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|root|Users|var|tmp)/)\S+")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{5,}(?!\d)")
SECRET_RE = re.compile(
    r"(?i)(password|passwd|token|secret|cookie|authorization|api[_-]?key)\s*[:=]\s*\S+"
)


def _sanitize_text(value: str) -> str:
    clean = SECRET_RE.sub(r"\1=<REDACTED>", str(value or ""))
    clean = URL_RE.sub("<URL>", clean)
    clean = PATH_RE.sub("<PATH>", clean)
    clean = LONG_NUMBER_RE.sub("<NUMBER>", clean)
    return " ".join(clean.split())[:500]


def _source_hash(text: str) -> str:
    payload = f"{HASH_NAMESPACE}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_arguments(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "")[:120]
        if not key:
            continue
        if raw_value is None or isinstance(raw_value, (bool, int, float)):
            output[key] = raw_value
            continue
        text = _sanitize_text(str(raw_value))
        output[key] = text if len(text) <= 120 else "<REDACTED_VALUE>"
    return output


def _parse_mapping(raw: str) -> dict[str, Any]:
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def extract(
    lines: Iterable[str], *, deduplicate_messages: bool = True
) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    seen: set[str] = set()
    for line in lines:
        message_match = MESSAGE_RE.search(line)
        if message_match:
            text = _sanitize_text(message_match.group("text"))
            normalized = text.casefold()
            if not text or (deduplicate_messages and normalized in seen):
                current = None
                continue
            seen.add(normalized)
            current = {
                "case_id": f"astrbot-shadow-{len(cases) + 1:06d}",
                "origin": "astrbot_production_shadow_candidate",
                "source_hash": _source_hash(text),
                "text": text,
                "message_type": "webchat",
                "observed_profile": "",
                "observed_tool_calls": [],
                "observed_result_statuses": [],
                "observed_model": "",
                "review_status": "pending_human_review",
            }
            cases.append(current)
            continue
        if current is None:
            continue
        model_match = MODEL_RE.search(line)
        if model_match:
            current["observed_model"] = model_match.group("model")[:120]
        route_match = ROUTE_RE.search(line)
        if route_match:
            current["observed_profile"] = route_match.group("profile")
            continue
        tool_match = TOOL_RE.search(line)
        if tool_match:
            payload = _parse_mapping(tool_match.group("arguments"))
            calls = current["observed_tool_calls"]
            if isinstance(calls, list):
                calls.append(
                    {
                        "service_ref": str(payload.get("service_ref") or "")[:120],
                        "capability": str(payload.get("capability") or "")[:120],
                        "argument_keys": sorted(
                            str(key)[:120]
                            for key in (payload.get("arguments") or {})
                            if isinstance(payload.get("arguments"), dict)
                        ),
                        "arguments": _safe_arguments(payload.get("arguments")),
                    }
                )
            continue
        result_match = RESULT_RE.search(line)
        if result_match:
            result = _parse_mapping(result_match.group("result"))
            statuses = current["observed_result_statuses"]
            if isinstance(statuses, list):
                statuses.append(str(result.get("status") or "unknown")[:40])
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract privacy-safe AstrBot capability shadow candidates."
    )
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--trace-jsonl", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    if args.output is None and args.trace_jsonl is None:
        raise SystemExit("astrbot_route_output_required")
    if args.input:
        lines = args.input.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = sys.stdin.read().splitlines()
    if args.output is not None:
        cases = extract(lines, deduplicate_messages=True)[: max(1, args.limit)]
        payload = {
            "fixture_kind": "astrbot_route_shadow_candidates",
            "review_status": "pending_human_review",
            "cases": cases,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"astrbot_route_candidates={len(cases)}:output={args.output}")
    if args.trace_jsonl is not None:
        if args.fixture is None or not args.provider:
            raise SystemExit("astrbot_trace_fixture_provider_required")
        trace_cases = extract(lines, deduplicate_messages=False)[: max(1, args.limit)]
        trace_rows = _build_trace_rows(
            trace_cases, args.fixture, args.provider, args.model
        )
        args.trace_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.trace_jsonl.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in trace_rows),
            encoding="utf-8",
        )
        print(f"astrbot_shadow_traces={len(trace_rows)}:output={args.trace_jsonl}")


def _build_trace_rows(
    candidates: list[dict[str, object]],
    fixture_path: Path,
    provider: str,
    model: str,
) -> list[dict[str, object]]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
    fixture_cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(fixture_cases, list):
        raise SystemExit("astrbot_trace_fixture_invalid")
    by_hash = {
        str(case.get("source_hash") or ""): str(case.get("case_id") or "")
        for case in fixture_cases
        if isinstance(case, dict)
    }
    attempts: dict[str, int] = {}
    rows = []
    for candidate in candidates:
        case_id = by_hash.get(str(candidate.get("source_hash") or ""))
        if not case_id:
            continue
        attempt = attempts.get(case_id, 0) + 1
        attempts[case_id] = attempt
        if attempt > 3:
            continue
        observed_model = str(candidate.get("observed_model") or model).strip()
        if not observed_model:
            raise SystemExit(f"astrbot_trace_model_missing={case_id}")
        rows.append(
            {
                "case_id": case_id,
                "attempt": attempt,
                "provider": provider,
                "model": observed_model,
                "tool_calls": [
                    {
                        "capability": str(call.get("capability") or ""),
                        "arguments": call.get("arguments") or {},
                    }
                    for call in candidate.get("observed_tool_calls", [])
                    if isinstance(call, dict) and call.get("capability")
                ],
            }
        )
    return rows


if __name__ == "__main__":
    main()
