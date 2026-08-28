from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


FIXTURE_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1
RUN_MANIFEST_SCHEMA_VERSION = 1
SAFE_SYNTHETIC_ID_RE = re.compile(r"1\d{4,8}")
ACCEPTANCE_INSTANCE_ALIAS_RE = re.compile(
    r"accept-ncqq-(?P<date>\d{8})-(?P<suffix>[a-z0-9]{8})"
)
FORBIDDEN_INSTANCE_ALIASES = frozenset({"arona", "plana", "codex-qr-test-07120029"})
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{5,}(?!\d)")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(?i)(authorization|api[_-]?key|access[_-]?token|password|passwd|secret|cookie)"
    r"\s*[:=]\s*\S+"
)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
APPROVAL_ID_RE = re.compile(r"\b[A-Z0-9]{6,16}\b")
ROUTE_RE = re.compile(
    r"Plana turn route:.*?turn=(?P<turn>[a-f0-9-]+).*?profile=(?P<profile>[a-z_]+)"
    r"(?:.*?tools=(?P<tools>\[[^\]]*\]))?",
    re.IGNORECASE,
)
TOOL_RE = re.compile(r"(?:使用工具：|Tool call:?)\s*(?P<tool>[a-zA-Z0-9_.-]+)")
NCQQ_WORKFLOW_RE = re.compile(
    r"(?:workflow|selected_workflow|action)\s*[=:]\s*['\"]?(?P<workflow>[a-z_]+)",
    re.IGNORECASE,
)


class MatchaAcceptanceError(ValueError):
    pass


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    messages: tuple[dict[str, Any], ...]
    expected: dict[str, Any]
    source_hash: str


def load_cases(path: Path) -> list[Case]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture_kind") != "ncqq_recovery_matcha_cases":
        raise MatchaAcceptanceError("fixture_kind_invalid")
    if payload.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise MatchaAcceptanceError("fixture_schema_version_invalid")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise MatchaAcceptanceError("fixture_cases_required")
    cases: list[Case] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise MatchaAcceptanceError("fixture_case_invalid")
        case_id = str(raw.get("case_id") or "").strip()
        if not re.fullmatch(r"[a-z0-9-]{8,80}", case_id) or case_id in seen:
            raise MatchaAcceptanceError(f"fixture_case_id_invalid:{case_id}")
        seen.add(case_id)
        messages = raw.get("messages")
        if not isinstance(messages, list) or not messages:
            raise MatchaAcceptanceError(f"fixture_messages_invalid:{case_id}")
        for message in messages:
            if not isinstance(message, dict) or not str(message.get("text") or "").strip():
                raise MatchaAcceptanceError(f"fixture_message_invalid:{case_id}")
        source_hash = str(raw.get("source_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise MatchaAcceptanceError(f"fixture_source_hash_invalid:{case_id}")
        expected = raw.get("expected")
        if not isinstance(expected, dict):
            raise MatchaAcceptanceError(f"fixture_expected_invalid:{case_id}")
        cases.append(
            Case(
                case_id=case_id,
                category=str(raw.get("category") or "unknown"),
                messages=tuple(messages),
                expected=expected,
                source_hash=source_hash,
            )
        )
    return cases


def require_synthetic_id(value: str, field: str) -> int:
    clean = str(value or "").strip()
    if SAFE_SYNTHETIC_ID_RE.fullmatch(clean) is None:
        raise MatchaAcceptanceError(f"{field}_must_be_synthetic_1xxxx")
    return int(clean)


def require_acceptance_instance_alias(value: str) -> str:
    clean = str(value or "").strip()
    if clean.casefold() in FORBIDDEN_INSTANCE_ALIASES:
        raise MatchaAcceptanceError(f"instance_alias_forbidden:{clean}")
    match = ACCEPTANCE_INSTANCE_ALIAS_RE.fullmatch(clean)
    if match is None:
        raise MatchaAcceptanceError("instance_alias_must_match_accept_ncqq_date_suffix")
    try:
        datetime.strptime(match.group("date"), "%Y%m%d")
    except ValueError as exc:
        raise MatchaAcceptanceError("instance_alias_date_invalid") from exc
    return clean


def render_text(template: str, instance_alias: str) -> str:
    return template.replace("{instance}", require_acceptance_instance_alias(instance_alias))


def onebot_group_event(
    *,
    bot_id: int,
    user_id: int,
    group_id: int,
    message_id: int,
    text: str,
    reply_message_id: int | None = None,
) -> dict[str, Any]:
    message: list[dict[str, Any]] = []
    if reply_message_id is not None:
        message.append({"type": "reply", "data": {"id": str(reply_message_id)}})
    message.append({"type": "text", "data": {"text": text}})
    return {
        "time": 0,
        "self_id": bot_id,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": message_id,
        "group_id": group_id,
        "user_id": user_id,
        "message": message,
        "raw_message": text,
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": "Matcha验收用户",
            "card": "Matcha验收成员",
            "role": "admin",
        },
    }


def sanitize_text(value: str, *, instance_alias: str = "") -> str:
    clean = ANSI_RE.sub("", str(value or ""))
    clean = SECRET_RE.sub(r"\1=<REDACTED>", clean)
    clean = URL_RE.sub("<URL>", clean)
    if instance_alias:
        clean = clean.replace(instance_alias, "<INSTANCE>")
    clean = APPROVAL_ID_RE.sub("<APPROVAL>", clean)
    clean = LONG_NUMBER_RE.sub("<ID>", clean)
    return " ".join(clean.split())[:500]


def extract_log_observations(
    lines: Iterable[str], *, instance_alias: str = ""
) -> dict[str, Any]:
    profiles: list[str] = []
    tools: list[str] = []
    workflows: list[str] = []
    approval_states: list[str] = []
    qrcode = False
    delivery_private = False
    errors: list[str] = []
    for raw_line in lines:
        line = ANSI_RE.sub("", raw_line)
        route = ROUTE_RE.search(line)
        if route:
            profiles.append(route.group("profile"))
            tools.extend(re.findall(r"['\"]([a-zA-Z0-9_.-]+)['\"]", route.group("tools") or ""))
        tool = TOOL_RE.search(line)
        if tool:
            tools.append(tool.group("tool"))
        workflow = NCQQ_WORKFLOW_RE.search(line)
        if workflow and "ncqq" in line.casefold():
            workflows.append(workflow.group("workflow"))
        lowered = line.casefold()
        if "approval" in lowered or "审批" in line:
            for state in ("pending", "executing", "completed", "rejected", "cancelled", "expired"):
                if state in lowered:
                    approval_states.append(state)
            if "取消" in line or "拒绝" in line:
                approval_states.append("cancelled")
            if "确认" in line or "批准" in line:
                approval_states.append("confirmed")
        if "qrcode" in lowered or "二维码" in line:
            qrcode = True
        if ("send_private_msg" in line or "private" in lowered) and qrcode:
            delivery_private = True
        if any(token in lowered for token in ("traceback", " exception", " failed", "error:")):
            safe = sanitize_text(line, instance_alias=instance_alias)
            if safe and safe not in errors:
                errors.append(safe)
    return {
        "profiles": stable_unique(profiles),
        "tools": stable_unique(tools),
        "workflows": stable_unique(workflows),
        "approval_states": stable_unique(approval_states),
        "qrcode_observed": qrcode,
        "private_delivery_observed": delivery_private,
        "errors": errors[:10],
    }


def stable_unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def hash_runtime_value(value: str) -> str:
    return hashlib.sha256(f"ncqq-matcha-v1\0{value}".encode()).hexdigest()


def assert_privacy_safe(value: Any, path: str = "report") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(token in lowered for token in ("token", "secret", "password", "cookie", "qq_id")):
                raise MatchaAcceptanceError(f"sensitive_report_key:{path}.{key}")
            assert_privacy_safe(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            assert_privacy_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        if URL_RE.search(value) or SECRET_RE.search(value) or LONG_NUMBER_RE.search(value):
            raise MatchaAcceptanceError(f"sensitive_report_value:{path}")


def write_safe_json(path: Path, payload: dict[str, Any]) -> None:
    assert_privacy_safe(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
