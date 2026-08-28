from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASTRBOT_PYTHON = Path(r"C:\git\AstrBot\.venv\Scripts\python.exe")
SOURCE_SUFFIXES = {".py", ".js", ".css", ".html"}
MAX_LINES = 500
TEMPLATE_PATTERN = re.compile(r"{{[A-Z][A-Z0-9_]*}}")
CODE_CHECKS = (
    "check_assistant_task_broker.py", "check_astrbot_kb_memory_lifecycle.py",
    "check_bridge_delivery_isolation.py", "check_codex_runner_shim.py",
    "check_codex_skill_materialization.py", "check_conversation_frame.py",
    "check_delivery_context.py",
    "check_dialogue_observer_memory_policy.py",
    "check_group_continuation.py", "check_group_session_isolation.py",
    "check_livingmemory_compat.py",
    "check_memory_kernel.py", "check_memory_maintenance_runtime.py",
    "check_message_anchor.py", "check_recall_gap_loop.py",
    "check_reminder_schedule.py",
    "check_remote_render_policy.py", "check_remote_task_cancellation.py",
    "check_remote_task_submission_guard.py",
    "check_task_session_concurrency.py",
    "check_tool_history_sanitizer.py", "check_tool_progress_policy.py",
    "check_config_defaults.py", "check_dialogue_analyzer.py",
    "check_resource_governance.py",
    "check_remote_execution_contract.py", "check_execution_audit_web.py",
    "check_astrbot_embed.py", "check_web_shell.py", "check_persona_mode_sync.py",
    "check_profile_proactive_jobs.py",
    "check_capability_probe.py",
    "check_domain_plugin_contracts.py", "check_ncqq_recovery_matcha.py",
    "check_integration_catalog.py", "check_integration_payload.py",
    "check_remote_execution_lifecycle.py", "check_companion_convergence.py",
    "check_final_convergence.py",
    "check_astrbot_plugin_family.py",
    "check_webhook_governance.py",
)
INTEGRATION_CHECKS = (
    "check_behavior_orchestrator.py", "check_chat_intent_policy.py",
    "check_conversational_prompt_profile.py", "check_dialogue_preflight_intent.py",
    "check_gallery_context.py", "check_memory_warehouse_http_only.py",
    "check_memory_retrieval.py", "check_search_result_policy.py",
    "check_unified_recall.py", "check_xiaowei_gallery_context.py",
    "check_ecosystem_compatibility.py",
)
LIVE_CHECKS = (
    "check_codex_production_gray.py",
    "check_xiaowei_behavior_replay.py",
)
MATRIX_ENTRYPOINTS = {"check_beta_release.py", "check_code_acceptance.py"}


def _bootstrap_astrbot_python() -> None:
    if os.environ.get("PLANA_CODE_ACCEPTANCE_BOOTSTRAPPED") == "1":
        return
    if not ASTRBOT_PYTHON.exists():
        raise SystemExit(f"astrbot_python_missing={ASTRBOT_PYTHON}")
    if Path(sys.executable).resolve() == ASTRBOT_PYTHON.resolve():
        return
    env = os.environ.copy()
    env["PLANA_CODE_ACCEPTANCE_BOOTSTRAPPED"] = "1"
    result = subprocess.run(
        [str(ASTRBOT_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=ROOT, env=env, check=False,
    )
    raise SystemExit(result.returncode)


def _run(label: str, command: list[str]) -> None:
    print(f"acceptance_run={label}", flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise SystemExit(f"acceptance_failed={label}:exit={result.returncode}")


def _repository_sources() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return sorted(
        ROOT / raw for raw in result.stdout.splitlines()
        if (ROOT / raw).is_file() and (ROOT / raw).suffix.lower() in SOURCE_SUFFIXES
    )


def _check_line_limits(paths: list[Path]) -> None:
    oversized = []
    for path in paths:
        try:
            lines = len(path.read_text(encoding="utf-8-sig").splitlines())
        except UnicodeDecodeError:
            continue
        if lines > MAX_LINES:
            oversized.append(f"{path.relative_to(ROOT).as_posix()}:{lines}")
    if oversized:
        raise SystemExit(f"source_line_limit_exceeded={oversized}")


def _check_templates(paths: list[Path]) -> None:
    unresolved = []
    for path in paths:
        if path.suffix.lower() not in {".html", ".css", ".js"}:
            continue
        if path == ROOT / "web" / "shell" / "template.html":
            continue
        matches = sorted(set(TEMPLATE_PATTERN.findall(path.read_text(encoding="utf-8-sig"))))
        if matches:
            unresolved.append(f"{path.relative_to(ROOT).as_posix()}:{matches}")
    if unresolved:
        raise SystemExit(f"unresolved_template_variables={unresolved}")
    page_path = ROOT / "web" / "page.py"
    spec = importlib.util.spec_from_file_location("plana_acceptance_web_page", page_path)
    if spec is None or spec.loader is None:
        raise SystemExit("dashboard_page_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = module.dashboard_html("/__plana_bridge_api__", bridge_mode=True)
    matches = sorted(set(TEMPLATE_PATTERN.findall(rendered)))
    if matches:
        raise SystemExit(f"rendered_dashboard_template_variables={matches}")


def _check_document_references() -> None:
    documents = (ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "web/dashboard_shell.md")
    missing = []
    pattern = re.compile(r"(?:python\s+)?(?:scripts[\\/][\w.-]+\.py|[\w./-]+\.md)")
    for document in documents:
        for match in pattern.findall(document.read_text(encoding="utf-8")):
            relative = match.split(maxsplit=1)[-1].replace("\\", "/")
            if relative.startswith("../") or (ROOT / relative).exists():
                continue
            sibling_matches = list(ROOT.parent.glob(f"astrbot_plugin_plana_*/scripts/{Path(relative).name}"))
            if not sibling_matches:
                missing.append(f"{document.name}:{relative}")
    if missing:
        raise SystemExit(f"documentation_reference_missing={missing}")


def _run_static_checks() -> None:
    sources = _repository_sources()
    python_files = [str(path.relative_to(ROOT)) for path in sources if path.suffix.lower() == ".py"]
    javascript_files = [str(path) for path in sources if path.suffix.lower() == ".js"]
    _run("compileall", [sys.executable, "-m", "compileall", "-q", "-f", *python_files])
    _run("ruff", [sys.executable, "-m", "ruff", "check", *python_files, "--select", "F401,F811,F821,F841"])
    node = shutil.which("node")
    if not node:
        raise SystemExit("node_missing")
    for path in javascript_files:
        _run(f"node_check:{Path(path).relative_to(ROOT).as_posix()}", [node, "--check", path])
    _check_line_limits(sources)
    _check_templates(sources)
    _check_document_references()
    _run("git_diff_check", ["git", "diff", "--check"])


def _run_script_matrix(names: tuple[str, ...]) -> None:
    missing = [name for name in names if not (ROOT / "scripts" / name).exists()]
    if missing:
        raise SystemExit(f"acceptance_script_missing={missing}")
    for name in names:
        _run(name, [sys.executable, str(ROOT / "scripts" / name)])


def _check_matrix_coverage() -> None:
    classified = set(CODE_CHECKS) | set(INTEGRATION_CHECKS) | set(LIVE_CHECKS)
    available = {path.name for path in (ROOT / "scripts").glob("check_*.py")}
    unclassified = sorted(available - classified - MATRIX_ENTRYPOINTS)
    missing = sorted(classified - available)
    if unclassified or missing:
        raise SystemExit(
            f"acceptance_matrix_drift=unclassified:{unclassified}:missing:{missing}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Plana Core acceptance checks by tier.")
    parser.add_argument("--tier", choices=("code", "integration", "live"), default="code")
    args = parser.parse_args()
    _bootstrap_astrbot_python()
    _check_matrix_coverage()
    _run_static_checks()
    _run_script_matrix(CODE_CHECKS)
    if args.tier in {"integration", "live"}:
        _run_script_matrix(INTEGRATION_CHECKS)
    if args.tier == "live":
        _run_script_matrix(LIVE_CHECKS)
    print(f"code_acceptance=ok:tier={args.tier}")


if __name__ == "__main__":
    main()
