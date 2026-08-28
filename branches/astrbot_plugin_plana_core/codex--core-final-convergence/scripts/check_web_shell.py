from __future__ import annotations

from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "page.py"
SHELL = ROOT / "web" / "shell"
VIEW_NAMES = {
    "overview.js",
    "memory-graph.js",
    "memory.js",
    "tasks.js",
    "capabilities.js",
    "resources.js",
    "settings.js",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    page = PAGE.read_text(encoding="utf-8")
    api = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
    template = (SHELL / "template.html").read_text(encoding="utf-8")
    styles = (SHELL / "styles.css").read_text(encoding="utf-8")
    app = (SHELL / "app.js").read_text(encoding="utf-8")
    i18n = (SHELL / "i18n.js").read_text(encoding="utf-8")
    preview = (ROOT / "scripts" / "preview_web.py").read_text(encoding="utf-8")
    views = {
        path.name: path.read_text(encoding="utf-8")
        for path in (SHELL / "views").glob("*.js")
    }
    all_text = "\n".join([page, template, styles, app, i18n, *views.values()])

    require(len(page.splitlines()) <= 80, "web_page_assembler_too_large")
    require(set(views) == VIEW_NAMES, f"web_view_modules={sorted(views)}")
    require("@lru_cache" in page and "VIEW_FILES" in page, "shell_source_cache_missing")
    require('"Cache-Control"] = "no-store, no-cache, must-revalidate"' in api, "dashboard_cache_policy_missing")
    require("{{STYLES}}" in template and "{{SCRIPTS}}" in template, "shell_inline_slots_missing")
    require('data-react-shell="plana-web-shell"' in template, "shell_marker_missing")
    require("web/assets.py" not in preview and "ASSETS_PATH" not in preview, "preview_uses_removed_asset_helper")

    sections = {
        'data-section="overview"',
        'data-section="memory"',
        'data-section="tasks"',
        'data-section="capabilities"',
        'data-section="resources"',
        'data-section="settings"',
    }
    missing_sections = sorted(item for item in sections if item not in template)
    require(not missing_sections, f"primary_sections_missing={missing_sections}")
    require(template.count('class="nav-item') == 6, "primary_navigation_must_have_six_items")
    require("mobile-nav-toggle" in template and "aria-expanded" in template, "mobile_navigation_missing")
    require("aria-current" in template and "title.focus()" in app, "navigation_focus_contract_missing")

    require("grid-template-columns:300px minmax(0,1fr)" in styles, "master_detail_layout_missing")
    require(".table-scroll{overflow-x:auto" in styles, "responsive_table_wrapper_missing")
    require("height:clamp(300px,58vh,560px)" in styles, "responsive_graph_height_missing")
    require(":focus-visible" in styles, "visible_focus_style_missing")
    require("prefers-reduced-motion" in styles, "reduced_motion_missing")

    capability = views["capabilities.js"]
    overview = views["overview.js"]
    require("data.domain_harness" in capability and "item.write_operations" in capability, "domain_harness_view_missing")
    require("ctx.tech(item)" in capability, "domain_harness_technical_fields_missing")
    require(".slice(0,160)" not in capability, "capability_description_still_truncated")
    require("plana_selected_domain" in capability, "domain_selection_persistence_missing")
    require("mobile-back" in capability, "capability_mobile_back_missing")
    require("Core 不会回退到内置领域清单" in capability, "domain_empty_state_missing")
    require("领域集成" in overview and "domainHarness.status === 'empty'" in overview, "overview_domain_status_missing")
    require("/api/capability-candidates" not in capability, "retired_candidate_ui_api_present")
    require("运行时安装或能力审批入口" in capability, "domain_integration_boundary_missing")

    memory = views["memory.js"]
    graph = views["memory-graph.js"]
    require("PlanaMemoryGraph.mount" in memory, "memory_graph_module_mount_missing")
    require("data-map-action=\"reset\"" in memory, "memory_graph_reset_control_missing")
    require("wheel" in graph and "pointermove" in graph, "memory_graph_roam_missing")
    require("neighbors" in graph and "relatedNodes" in graph, "memory_graph_adjacency_focus_missing")
    require("aria-pressed" in graph, "memory_graph_label_toggle_state_missing")
    require("/api/memory-scopes" in memory, "memory_scope_selector_api_missing")
    require("data-memory-scope" in memory, "memory_scope_selector_missing")
    require("memory-strip-list" in memory and "data-memory-toggle" in memory, "memory_strip_navigation_missing")
    require("item.kind" in memory and "item.payload" in memory, "memory_feedback_payload_mapping_missing")
    require("data-process-scope" in memory and "dataset.confirmed" in memory, "memory_feedback_confirmation_missing")
    require("feedbackEditor" in memory and "gapEditor" in memory, "memory_correction_editor_missing")
    require("/api/feedback/update" in memory, "memory_feedback_update_action_missing")
    require("/api/feedback/process-item" in memory, "memory_feedback_single_process_missing")
    require("/api/feedback/dismiss" in memory, "memory_feedback_dismiss_missing")
    require("data-quality-action=\"propose\"" in memory, "recall_gap_editor_missing")
    require("confirm: true" in memory and "data-confirmed" in memory, "memory_correction_confirmation_missing")

    tasks = views["tasks.js"]
    require("tasks.approvals" in tasks and "tasks.todos" in tasks and "tasks.codex" in tasks, "task_subviews_missing")
    require("/api/feedback" in tasks and "/api/tasks" in tasks and "/api/proactive" in tasks, "companion_task_sources_missing")
    require("/api/remote-tasks" in tasks and "Codex 运行" in tasks, "codex_task_summary_missing")
    require("/api/workflows" not in tasks and "workflow-create" not in tasks, "retired_workflow_ui_present")

    resources = views["resources.js"]
    require("Codex Runner" in resources, "codex_runner_resource_copy_missing")
    require("state.integrations" in resources and "gateway.status" in resources, "integration_gateway_status_missing")
    require("访问边界" in resources, "resource_access_boundary_missing")
    require("resources.remote" in resources and "resources.audit" not in resources, "resource_subviews_not_converged")
    require("remote-workspace" in resources and "data-remote-filter" in resources, "remote_task_master_detail_missing")
    require("/api/remote-tasks/cancel" in resources and "再次点击确认取消" in resources, "remote_task_cancel_confirmation_missing")
    require("data-remote-action-result" in resources and "reconciled_terminal" in resources and "state.remoteNotice" in resources, "remote_task_cancel_feedback_missing")
    require("/api/remote-learning" not in resources and "Skill 版本" not in resources, "retired_learning_audit_ui_present")
    require("Hermes（历史）" not in resources, "retired_executor_brand_visible")
    require("domain-refresh" in capability and "ctx.api('/api/domains')" in capability, "domain_harness_manual_refresh_missing")
    require("health-grid" in overview and "overview-main-grid" in overview, "overview_health_layout_missing")

    settings = views["settings.js"]
    require("detailText" in settings, "maintenance_detail_formatter_missing")
    require("data-confirmed" in settings and "confirm: true" in settings, "maintenance_confirmation_missing")
    require("/api/diagnostics" in settings, "diagnostics_api_missing")
    require("diagnostic-service-grid" in settings and "diagnostic-findings" in settings, "diagnostics_layout_missing")
    require("ctx.tech(data.technical" in settings, "diagnostics_technical_appendix_missing")
    require("陪伴服务" in overview and "data.gallery" in overview, "companion_overview_missing")
    require("data.build" in overview and "build.build_id" in overview, "core_build_overview_missing")
    require("gallery.local_loopback_only" in overview, "gallery_loopback_status_missing")
    require("section: 'settings'" in overview and "subview: 'diagnostics'" in overview, "gallery_health_navigation_missing")
    require("Memory Warehouse" in overview and "plana.memory_warehouse" in overview, "warehouse_health_overview_missing")
    require("candidate_counts" not in settings and "候选治理" not in settings, "retired_candidate_diagnostics_present")
    require("data.user_id" in memory, "profile_scope_identity_fallback_missing")

    retired_shell_markers = {
        "/api/workflows": "workflow API",
        "/api/capability-candidates": "candidate API",
        "tasks.workflows": "workflow navigation",
        "capabilities.governance": "candidate navigation",
        "resources.audit": "learning audit navigation",
        "Hermes（历史）": "retired executor brand",
    }
    retired_violations = [label for marker, label in retired_shell_markers.items() if marker in "\n".join([template, i18n, *views.values()])]
    require(not retired_violations, f"retired_web_surfaces={retired_violations}")

    scope_spec = spec_from_file_location(
        "plana_memory_scope_payload",
        ROOT / "web" / "memory_scope_payload.py",
    )
    require(scope_spec is not None and scope_spec.loader is not None, "memory_scope_presenter_import_failed")
    scope_module = module_from_spec(scope_spec)
    scope_spec.loader.exec_module(scope_module)
    require(
        scope_module.memory_scope_user_id("llonebot:FriendMessage:924781982")
        == "aiocqhttp:924781982",
        "friend_scope_identity_invalid",
    )
    require(
        scope_module.memory_scope_user_id(
            "llonebot:GroupMessage:644572093_906678215"
        )
        == "aiocqhttp:644572093",
        "group_scope_identity_invalid",
    )
    require(
        scope_module.memory_scope_user_id(
            "llonebot:GroupMessage:1195631102_1006784035"
        )
        == "aiocqhttp:1195631102",
        "second_group_scope_identity_invalid",
    )
    require(
        scope_module.memory_scope_user_id(
            "webchat:FriendMessage:webchat!root!a9e01a59-ad5e-43d0-89f4-bf923b41301c"
        )
        == "webchat:root",
        "web_scope_identity_invalid",
    )

    inspectors = (ROOT / "web" / "inspectors.py").read_text(encoding="utf-8")
    require(
        'get_person_profile(scope, "", safe_limit)' not in inspectors,
        "profile_identity_still_inferred_from_global_fallback",
    )
    require(
        "subject != user_id" in inspectors and "local_semantics" in inspectors,
        "profile_semantic_identity_guard_missing",
    )

    domain_spec = spec_from_file_location("plana_domain_harness_payload", ROOT / "web" / "domain_harness_payload.py")
    require(domain_spec is not None and domain_spec.loader is not None, "domain_harness_presenter_import_failed")
    domain_module = module_from_spec(domain_spec)
    domain_spec.loader.exec_module(domain_module)
    empty_domains = domain_module.build_domain_harness_web_payload(SimpleNamespace(astr_context=SimpleNamespace(get_all_stars=lambda: [])))
    require(empty_domains["status"] == "empty" and empty_domains["items"] == [], "domain_harness_empty_state_invalid")
    plugin = SimpleNamespace(domain_harness_descriptors=lambda: [{"schema_version": 1, "domain_id": "media", "owner": "Media Plugin", "profile": "media", "tool_name": "media_dispatch", "read_operations": ["list"], "write_operations": ["update"], "direct_dispatch": True}])
    discovered = domain_module.build_domain_harness_web_payload(SimpleNamespace(astr_context=SimpleNamespace(get_all_stars=lambda: [SimpleNamespace(activated=True, name="media_plugin", star_cls=plugin)])))
    require(discovered["summary"]["discovered"] == 1, "domain_harness_discovery_invalid")
    require(discovered["summary"]["confirmation_governed"] == 1, "domain_harness_confirmation_summary_invalid")

    remote_spec = spec_from_file_location(
        "plana_remote_task_payload",
        ROOT / "web" / "remote_task_payload.py",
    )
    require(remote_spec is not None and remote_spec.loader is not None, "remote_task_presenter_import_failed")
    remote_module = module_from_spec(remote_spec)
    remote_spec.loader.exec_module(remote_module)
    codex_tasks = remote_module.build_remote_task_web_payload(
        {},
        [{
            "request_id": "codex-test",
            "status": "running",
            "lane": "interactive",
            "payload": {
                "contract_version": "plana.codex.delegate.v1",
                "type": "codex_delegate",
                "engine": "codex",
                "execution_profile": "coding_quality",
                "profile_revision": 3,
                "constraints": {"authorization": "user_confirmed"},
            },
            "runner_run_id": "codex-run-1",
            "created_at": 100,
            "updated_at": 100,
        }],
        now=100,
    )
    codex_display = codex_tasks["display_items"][0]["display"]
    require(codex_display["executor"] == "Codex CLI", "codex_executor_label_missing")
    require(codex_display["execution_profile"] == "coding_quality", "codex_profile_missing")
    require(codex_display["workspace"] == "", "codex_workspace_should_be_runner_reported")
    require(codex_display["approval"] == "用户已确认", "codex_approval_missing")
    require(codex_tasks["summary"]["executor"]["key"] == "codex", "codex_executor_summary_missing")
    require("hermes" not in resources.casefold(), "retired_executor_copy_present")
    require("hermes" not in overview.casefold(), "retired_overview_copy_present")
    require("Codex CLI" in resources and "Codex Runner" in overview, "codex_web_copy_missing")
    require("/api/integrations" in resources, "adapter_gateway_integration_api_missing")
    require("resources.gateway" in i18n and "resources.bindings" in i18n, "integration_subnavigation_missing")
    require("gateway.title" in resources and "资源绑定" in resources, "integration_information_architecture_missing")
    require("capabilityCard" in resources and "gateway.arguments.one_of" in resources, "integration_capability_contract_missing")
    require("gateway.capability.ani_list.title" in i18n, "integration_zh_translation_missing")
    require("List anime subscriptions" in i18n, "integration_en_translation_missing")
    require("gateway-readiness" in styles and "capability-contract" in styles, "integration_detail_styles_missing")
    require("data-jump-subview=\"gateway\"" in settings, "settings_gateway_navigation_missing")

    require("function storageGet" in app and "function storageSet" in app, "sandbox_storage_wrapper_missing")
    require("window.AstrBotPluginPage" in app, "plugin_page_bridge_missing")
    require("/__plana_bridge_api__" in app, "bridge_api_sentinel_missing")
    require("const normalized=" in app, "bridge_payload_normalizer_missing")
    require("showError" in app and "retry-view" in app, "user_error_retry_missing")
    require("aria-busy" in app and "skeleton" in styles, "loading_state_missing")

    forbidden = {
        "http://": "external http URL",
        "https://": "external https URL",
        "document.write": "document rewrite",
        "window.location.replace": "plugin page redirect",
        "alert(": "blocking alert",
    }
    violations = [label for snippet, label in forbidden.items() if snippet in all_text]
    require(not violations, f"web_shell_forbidden={violations}")
    print("web_shell_check=ok")


if __name__ == "__main__":
    main()
