from __future__ import annotations

import re
import hashlib
import json
from typing import Any

from .models import Finding, ScanResult, ScanVerdict, TrustLevel

SCANNER_VERSION = "plana.skill.scanner.v1"

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_TRUST_LEVELS: set[TrustLevel] = {
    "builtin",
    "trusted",
    "community",
    "agent-created",
}

_PATTERNS: list[tuple[str, str, str, str, str]] = [
    (
        r"ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+instructions",
        "prompt_injection_ignore",
        "critical",
        "injection",
        "attempts to override previous instructions",
    ),
    (
        r"do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user",
        "deception_hide",
        "critical",
        "injection",
        "instructs the assistant to hide information from the user",
    ),
    (
        r"output\s+(?:\w+\s+)*(system|initial)\s+prompt",
        "leak_system_prompt",
        "high",
        "injection",
        "attempts to extract system prompt content",
    ),
    (
        r"os\.environ\s*\.get\s*\(\s*[\"'][^\"']*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)",
        "python_environ_secret",
        "critical",
        "exfiltration",
        "reads secret-shaped environment variables",
    ),
    (
        r"(curl|wget|httpx?\.get|requests\.get|fetch)\s*[\(]?\s*[\"']https?://",
        "remote_fetch",
        "medium",
        "network",
        "fetches remote resources at runtime",
    ),
    (
        r"webhook\.site|requestbin\.com|pipedream\.net|hookbin\.com",
        "exfil_service",
        "high",
        "network",
        "references a common exfiltration or webhook testing service",
    ),
    (
        r"rm\s+-rf\s+/",
        "destructive_root_rm",
        "critical",
        "destructive",
        "recursive delete from root",
    ),
    (
        r"\bmkfs\b|\bdd\b[^\n]*\bof=/dev/",
        "disk_destroy",
        "critical",
        "destructive",
        "formats or overwrites a block device",
    ),
    (
        r"subprocess\.(run|call|Popen|check_output)\s*\(",
        "python_subprocess",
        "medium",
        "execution",
        "executes subprocesses",
    ),
    (
        r"os\.system\s*\(|os\.popen\s*\(",
        "python_shell_exec",
        "high",
        "execution",
        "executes shell commands from Python",
    ),
    (
        r"child_process\.(exec|spawn|fork)\s*\(",
        "node_child_process",
        "high",
        "execution",
        "executes child processes from Node.js",
    ),
    (
        r"curl\s+[^\n]*\|\s*(ba)?sh|wget\s+[^\n]*-O\s*-\s*\|\s*(ba)?sh",
        "download_execute",
        "critical",
        "supply_chain",
        "downloads and executes remote shell content",
    ),
    (
        r"pip\s+install\s+(?!-r\s)(?!.*==)|npm\s+install\s+(?!.*@\d)",
        "unpinned_install",
        "medium",
        "supply_chain",
        "installs unpinned dependencies",
    ),
    (
        r"\bcrontab\b|systemd.*\.service|systemctl\s+(enable|start)",
        "persistence",
        "medium",
        "persistence",
        "references persistence mechanisms",
    ),
    (
        r"authorized_keys|/etc/sudoers|visudo",
        "privilege_persistence",
        "critical",
        "persistence",
        "references privilege or SSH persistence targets",
    ),
]

_COMPILED = [
    (re.compile(pattern, re.IGNORECASE | re.DOTALL), pattern_id, severity, category, description)
    for pattern, pattern_id, severity, category, description in _PATTERNS
]

RULESET_HASH = "sha256:" + hashlib.sha256(
    json.dumps(_PATTERNS, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
).hexdigest()

_INVISIBLE_CHARS = {
    "\u200b": "zero-width space",
    "\u200c": "zero-width non-joiner",
    "\u200d": "zero-width joiner",
    "\u2060": "word joiner",
    "\ufeff": "BOM/zero-width no-break space",
    "\u202a": "LTR embedding",
    "\u202b": "RTL embedding",
    "\u202c": "pop directional",
    "\u202d": "LTR override",
    "\u202e": "RTL override",
    "\u2066": "LTR isolate",
    "\u2067": "RTL isolate",
    "\u2068": "first strong isolate",
    "\u2069": "pop directional isolate",
}


class SkillScanner:
    """Static scanner for generated or imported SKILL.md content."""

    def scan(self, body: str, *, trust_level: str = "agent-created") -> ScanResult:
        trust = self._trust_level(trust_level)
        findings: list[Finding] = []
        lines = body.splitlines() or [body]
        for line_no, line in enumerate(lines, 1):
            for pattern, pattern_id, severity, category, description in _COMPILED:
                match = pattern.search(line)
                if match:
                    findings.append(
                        Finding(
                            pattern_id=pattern_id,
                            severity=severity,
                            category=category,
                            line=line_no,
                            match=match.group(0),
                            description=description,
                        )
                    )
            for char, label in _INVISIBLE_CHARS.items():
                if char in line:
                    findings.append(
                        Finding(
                            pattern_id="invisible_unicode",
                            severity="high",
                            category="injection",
                            line=line_no,
                            match=f"U+{ord(char):04X} ({label})",
                            description="contains invisible unicode control characters",
                        )
                    )
                    break
        verdict = self._verdict(findings, trust)
        summary = self._summary(verdict, findings, trust)
        return ScanResult(
            verdict=verdict,
            trust_level=trust,
            findings=findings,
            summary=summary,
            scanner_version=SCANNER_VERSION,
            ruleset_hash=RULESET_HASH,
        )

    def _trust_level(self, value: str) -> TrustLevel:
        clean = str(value or "agent-created").strip().lower()
        return clean if clean in _TRUST_LEVELS else "agent-created"  # type: ignore[return-value]

    def _verdict(self, findings: list[Finding], trust: TrustLevel) -> ScanVerdict:
        if not findings:
            return "safe"
        max_score = max(_SEVERITY_ORDER.get(item.severity, 0) for item in findings)
        if max_score >= _SEVERITY_ORDER["high"]:
            return "dangerous"
        if trust == "community":
            return "dangerous"
        return "caution"

    def _summary(self, verdict: ScanVerdict, findings: list[Finding], trust: TrustLevel) -> str:
        if not findings:
            return f"{verdict}: no static findings for trust={trust}"
        categories: dict[str, int] = {}
        for finding in findings:
            categories[finding.category] = categories.get(finding.category, 0) + 1
        parts = ", ".join(f"{key}={value}" for key, value in sorted(categories.items()))
        return f"{verdict}: {len(findings)} finding(s), {parts}, trust={trust}"


def scan_payload(body: str, trust_level: str) -> dict[str, Any]:
    return SkillScanner().scan(body, trust_level=trust_level).to_dict()
