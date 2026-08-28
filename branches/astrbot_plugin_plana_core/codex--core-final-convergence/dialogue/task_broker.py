from __future__ import annotations

from typing import Any

from ..execution import ExecutionContextRegistry
from ..utils.intent_patterns import (
    looks_like_long_task_request,
    looks_like_service_discussion_request,
    native_tool_profile,
)
from .domain_contracts import DOMAIN_PLUGINS
from .domain_tool_route import DOMAIN_TOOL_PROFILES
from .remote_task import RemoteTaskDelegator
from .task_broker_models import AssistantTaskRequest, AssistantTaskResult
from .task_broker_support import AssistantTaskRouterSupportMixin
from .task_intent_classifier import TaskIntentClassifier
from .task_response_composer import TaskResponseComposer
from .task_route_decider import TaskRouteDecider
from .task_session import TaskSessionStore
from .task_session_service import TaskSessionService


class AssistantTaskRouter(AssistantTaskRouterSupportMixin):
    """Route a turn to one domain tool or governed Codex execution."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        database = getattr(getattr(runtime, "storage", None), "db", None)
        try:
            frame_ttl = int(runtime.config.get("assistant_conversation_frame_ttl_seconds", 180))
        except (TypeError, ValueError):
            frame_ttl = 180
        self.sessions = TaskSessionStore(database, ttl_seconds=frame_ttl)
        self.session_service = TaskSessionService(self.sessions)
        self.intent_classifier = TaskIntentClassifier()
        self.route_decider = TaskRouteDecider()
        self.composer = TaskResponseComposer()
        self.remote = RemoteTaskDelegator(runtime)
        self.execution_contexts = ExecutionContextRegistry()
        setattr(runtime, "assistant_task_sessions", self.sessions)
        setattr(runtime, "remote_task_delegator", self.remote)
        setattr(runtime, "execution_context_registry", self.execution_contexts)

    async def handle(
        self,
        request: AssistantTaskRequest,
        provider: Any = None,
    ) -> AssistantTaskResult:
        del provider
        if not bool(self.runtime.config.get("assistant_task_enabled", True)):
            return AssistantTaskResult(reason="assistant_task_disabled")
        text = " ".join(request.text.split())
        scope_id = str(request.turn_context.scope_id or "global")
        actor_id = str(request.turn_context.actor_id or "user")

        natural = await self.session_service.handle_natural_action(
            text=text,
            event=request.event,
            scope_id=scope_id,
            actor_id=actor_id,
            runtime=self.runtime,
            composer=self.composer,
            remote=self.remote,
        )
        if natural.handled:
            return AssistantTaskResult(
                natural.handled,
                natural.reply,
                natural.stop_event,
                natural.reason,
                natural.render_document,
            )

        if looks_like_service_discussion_request(text) and not looks_like_long_task_request(text):
            return AssistantTaskResult(reason="service_discussion_direct_answer")

        profile = native_tool_profile(text)
        descriptor = DOMAIN_PLUGINS.for_profile(profile) if profile in DOMAIN_TOOL_PROFILES else None
        if descriptor is not None:
            setattr(request.event, "_plana_native_tool_profile", descriptor.profile)
            setattr(request.event, "_plana_expected_service_ref", descriptor.service_ref)
            setattr(
                request.event,
                "_plana_expected_capability",
                f"{descriptor.domain_id}.{descriptor.dispatch_workflow}",
            )
            self._record(
                request,
                scope_id,
                actor_id,
                action="domain_tool",
                capability=f"{descriptor.domain_id}.{descriptor.dispatch_workflow}",
                status="continued",
                reason="single_domain_plugin",
                route_name="domain_tool",
                tool_profile=descriptor.profile,
                risk_class="domain_governed",
            )
            return AssistantTaskResult(
                handled=False,
                stop_event=False,
                reason="single_domain_plugin_tool",
            )

        if request.decision.intent != "tool_execution_candidate":
            return AssistantTaskResult(reason="not_task_broker_route")
        capability = self.intent_classifier.classify(
            self.runtime,
            request.text,
            request.decision.intent,
        )
        route = self.route_decider.decide(self.runtime, request.text, capability)
        if route.action == "handoff_llm_tool":
            return self._handoff_llm_tool(request, scope_id, actor_id, route)
        return self._delegate_remote(request, scope_id, actor_id, route)


AssistantTaskBroker = AssistantTaskRouter
