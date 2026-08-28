from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    routes = (ROOT / "web" / "routes.py").read_text(encoding="utf-8")
    api = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
    tasks = (ROOT / "web" / "shell" / "views" / "tasks.js").read_text(encoding="utf-8")
    for retired in (
        "/plana/api/workflows",
        "/plana/api/capability-candidates",
        "api_workflow_confirm",
        "api_workflow_cancel",
    ):
        require(retired not in routes + api, f"retired_execution_web_surface={retired}")
    require('"/plana/api/tasks"' in routes, "task_session_route_missing")
    require('"/plana/api/remote-tasks"' in routes, "codex_route_missing")
    require("recent_traces" in api, "task_session_trace_source_missing")
    for needle in ("id: 'approvals'", "id: 'todos'", "id: 'codex'", "/api/remote-tasks?limit=50"):
        require(needle in tasks, f"task_view_missing={needle}")
    print("execution_audit_web_check=ok")


if __name__ == "__main__":
    main()
