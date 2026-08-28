from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("main.py", "plugin", "dialogue", "execution", "utils", "web")
FORBIDDEN = (
    "plana.hermes.",
    "hermes_delegate",
    "plana_secretary",
    "plana_service_query",
    "plana_request_execution_handoff",
    "secretary_skill_center",
    "voice_synthesis_url",
    "SecretaryWorkflowKernel",
    "SecretaryTurnAnalyzer",
    "enable_secretary_workflows",
    "workflow_request",
    "command.run_confirmed",
    "hermes_request_id",
    "workflow_candidate",
    "pending_workflow",
    "plana_qbittorrent",
    "qb_plugin",
    '"delegate_version": 2',
    "ExecutionEnvelope",
    "execution_envelope",
    "learning_context",
    "capability_registry",
    "sandbox/workflow",
)


def production_text() -> str:
    chunks: list[str] = []
    for name in PRODUCTION_DIRS:
        path = ROOT / name
        paths = [path] if path.is_file() else sorted(path.rglob("*.py")) + sorted(path.rglob("*.js"))
        for candidate in paths:
            chunks.append(candidate.read_text(encoding="utf-8-sig"))
    return "\n".join(chunks)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    source = production_text()
    for marker in FORBIDDEN:
        require(marker not in source, f"retired_production_marker={marker}")
    require(not (ROOT / "plugin" / "voice.py").exists(), "voice_client_present")
    require(not (ROOT / "dialogue" / "remote_learning.py").exists(), "remote_learning_store_present")
    require("plana.memory_warehouse.v1" in (ROOT / "memory" / "warehouse_client.py").read_text(encoding="utf-8"), "warehouse_contract_missing")
    routes = (ROOT / "web" / "routes.py").read_text(encoding="utf-8")
    shell = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "web" / "shell").rglob("*.js"))
    ) + (ROOT / "web" / "shell" / "template.html").read_text(encoding="utf-8")
    require("capability-candidates" not in routes, "candidate_route_present")
    require("skill-center" not in routes and "/api/skills" not in routes, "retired_skill_web_route_present")
    for route in (
        "/plana/api/workflows",
        "/plana/api/workflows/run",
        "/plana/api/capability-candidates",
    ):
        require(route not in routes, f"retired_route_present={route}")
        require(route.removeprefix("/plana") not in shell, f"retired_route_exposed_in_shell={route}")
    require("Hermes（历史）" not in shell, "retired_executor_brand_exposed")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    branch_contract = "\n".join((readme, architecture))
    require("codex/core-governed" in branch_contract and "`main`（公开分支）" in branch_contract, "domain_branch_model_missing")
    require("共享业务内核" in branch_contract and "descriptor、proposal/lease adapter、确认接线" in branch_contract, "shared_domain_kernel_boundary_missing")
    require("两个插件版本" in branch_contract and "两套业务代码" in branch_contract, "duplicate_plugin_implementation_warning_missing")
    print("companion_convergence_check=ok")


if __name__ == "__main__":
    main()
