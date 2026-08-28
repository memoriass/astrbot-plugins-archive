from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from quart import jsonify

from ..dialogue.entry_filters import get_active_plugin


PLUGIN_PAGE_API_PREFIX = "/astrbot_plugin_plana_core"
COMPATIBILITY_ROUTES = frozenset(
    {
        "/plana/api/retrieve-test",
        "/plana/api/bridge-status",
        "/plana/api/context-preview",
    }
)

ROUTES = (
    ("/plana/dashboard", "serve_dashboard", ["GET"], "Dashboard HTML page"),
    ("/plana/api/auth-info", "api_auth_info", ["GET"], "Dashboard auth info"),
    ("/plana/api/overview", "api_overview", ["GET"], "Overview JSON"),
    ("/plana/api/resources", "api_resources", ["GET"], "Resource governance JSON"),
    ("/plana/api/integrations", "api_integrations", ["GET"], "Adapter Gateway integrations JSON"),
    ("/plana/api/domains", "api_domains", ["GET"], "Domain plugin catalog JSON"),
    ("/plana/api/webhook", "api_webhook", ["GET"], "Webhook companion governance JSON"),
    ("/plana/api/webhook/policy", "api_webhook_policy", ["POST"], "Update Webhook source policy"),
    ("/plana/api/webhook/replay", "api_webhook_replay", ["POST"], "Replay failed Webhook event"),
    ("/plana/api/diagnostics", "api_diagnostics", ["GET"], "Operator diagnostics JSON"),
    ("/plana/api/remote-tasks", "api_remote_tasks", ["GET"], "Remote task runs JSON"),
    ("/plana/api/remote-tasks/cancel", "api_remote_task_cancel", ["POST"], "Cancel remote task"),
    ("/plana/api/memories", "api_memories", ["GET"], "Memories JSON"),
    ("/plana/api/memory-scopes", "api_memory_scopes", ["GET"], "Memory scope summaries"),
    ("/plana/api/retrieve-test", "api_retrieve_test", ["GET"], "Retrieve lab JSON"),
    ("/plana/api/profile", "api_profile", ["GET"], "Profile JSON"),
    ("/plana/api/bridge-status", "api_bridge_status", ["GET"], "Bridge status JSON"),
    ("/plana/api/context-preview", "api_context_preview", ["GET"], "Context preview JSON"),
    ("/plana/api/concepts", "api_concepts", ["GET"], "Concepts JSON"),
    ("/plana/api/relations", "api_relations", ["GET"], "Relations JSON"),
    ("/plana/api/tasks", "api_tasks", ["GET"], "Tasks JSON"),
    ("/plana/api/maintenance-status", "api_maintenance_status", ["GET"], "Maintenance status JSON"),
    ("/plana/api/backup", "api_maintenance_backup", ["POST"], "Create maintenance backup"),
    ("/plana/api/rebuild-indexes", "api_maintenance_rebuild_indexes", ["POST"], "Rebuild memory indexes"),
    ("/plana/api/maintain", "api_maintain", ["POST"], "Trigger maintenance"),
    ("/plana/api/proactive", "api_proactive_list", ["GET"], "Proactive tasks list"),
    ("/plana/api/feedback", "api_feedback_list", ["GET"], "Feedback queue list"),
    ("/plana/api/recall-gaps", "api_recall_gaps", ["GET"], "Recall gap list"),
    ("/plana/api/recall-gaps/propose", "api_recall_gap_propose", ["POST"], "Queue recall gap memory candidate"),
    ("/plana/api/feedback/process", "api_feedback_process", ["POST"], "Process pending memory feedback"),
    ("/plana/api/feedback/update", "api_feedback_update", ["POST"], "Update pending memory feedback"),
    ("/plana/api/feedback/process-item", "api_feedback_process_item", ["POST"], "Process one pending memory feedback item"),
    ("/plana/api/feedback/dismiss", "api_feedback_dismiss", ["POST"], "Dismiss pending memory feedback"),
)


def register_dashboard_routes(plugin: Any) -> None:
    api = getattr(plugin, "_web_api", None)
    if api is None:
        return
    routes = [
        (*route, "compatibility" if route[0] in COMPATIBILITY_ROUTES else "dashboard")
        for route in ROUTES
    ]
    routes.extend(
        (
            PLUGIN_PAGE_API_PREFIX + route.removeprefix("/plana"),
            handler_name,
            methods,
            f"{description} (plugin page bridge alias)",
            "bridge/external",
        )
        for route, handler_name, methods, description in ROUTES
    )
    for route, handler_name, methods, description, usage in routes:
        handler = guard_plugin_handler(plugin, getattr(api, handler_name))
        plugin.context.register_web_api(
            route,
            handler,
            methods,
            f"{description} [{usage}]",
        )


def guard_plugin_handler(
    plugin: Any,
    handler: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    @wraps(handler)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        runtime = getattr(plugin, "runtime", None)
        if bool(getattr(plugin, "_terminating", False)):
            return jsonify({"ok": False, "error": "plugin_terminating"}), 503
        if runtime is None or not bool(getattr(runtime, "enabled", False)):
            return jsonify({"ok": False, "error": "plugin_disabled"}), 503
        if get_active_plugin() is not plugin:
            return jsonify({"ok": False, "error": "plugin_inactive"}), 503
        return await handler(*args, **kwargs)

    return guarded
