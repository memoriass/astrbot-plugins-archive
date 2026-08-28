from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..dialogue.domain_tool_route import (
    DOMAIN_TOOL_PROFILES,
    normalize_domain_tool_arguments,
)
from ..dialogue.domain_contracts import DOMAIN_PLUGINS
from ..dialogue.message_anchor import register_sent_message_anchors
from ..dialogue.tool_policy import tool_profile_for_text
from ..utils.intent_patterns import looks_like_service_discussion_request
from .domain_routing import DomainRoutingMixin
from .gallery_delivery import GalleryReactionDeliveryMixin
from .plugin_web import PlanaNativeSearchTool
from ..presentation import (
    finalize_search_response,
    is_artifact_resend_request,
    recommendation_document,
    render_document_to_file,
    render_dialogue_result,
)
from ..presentation.search_results import search_query_from_message


class PlanaPluginEventMixin(DomainRoutingMixin, GalleryReactionDeliveryMixin):
    async def _handle_passive_observe_message(self, event: AstrMessageEvent):
        return

    def _schedule_passive_dialogue_observe(self, event: AstrMessageEvent) -> None:
        if self._terminating:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.dialogue.observe_message(event)
            return
        task = loop.create_task(self._passive_dialogue_observe(event))
        self._passive_observe_tasks.add(task)
        task.add_done_callback(self._passive_observe_tasks.discard)
        task.add_done_callback(self._log_passive_observe_error)

    async def _passive_dialogue_observe(self, event: AstrMessageEvent) -> None:
        if self._terminating:
            return
        if not await self._session_allows_passive_dialogue_observe(event):
            return
        if self._terminating:
            return
        self.dialogue.observe_message(event)

    async def _session_allows_passive_dialogue_observe(
        self,
        event: AstrMessageEvent,
    ) -> bool:
        session_id = str(getattr(event, "unified_msg_origin", "") or "")
        if not session_id:
            return True
        try:
            from astrbot.core.star.session_llm_manager import SessionServiceManager
            from astrbot.core.star.session_plugin_manager import SessionPluginManager

            if not await SessionServiceManager.is_session_enabled(session_id):
                return False
            for plugin_name in self._SESSION_PLUGIN_NAMES:
                if not await SessionPluginManager.is_plugin_enabled_for_session(
                    session_id,
                    plugin_name,
                ):
                    return False
        except Exception:  # noqa: BLE001
            logger.debug("Plana passive observe session check skipped", exc_info=True)
        return True

    def _log_passive_observe_error(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            logger.warning("Plana passive dialogue observe failed", exc_info=True)

    async def _handle_active_message(self, event: AstrMessageEvent):
        resend = self._resend_artifact_result(event)
        if resend is not None:
            setattr(event, "_plana_anchor_outbound", True)
            yield resend
            event.stop_event()
            return
        profile = self._prepare_native_turn(event)
        if profile == "search":
            setattr(event, "_plana_anchor_outbound", True)
            await self._execute_native_search_turn(event)
            return
        active_profile = profile or str(
            getattr(event, "_plana_native_tool_profile", "") or ""
        )
        descriptor = DOMAIN_PLUGINS.for_profile(active_profile)
        if descriptor is not None and descriptor.direct_dispatch:
            setattr(event, "_plana_anchor_outbound", True)
            async for result in self._execute_domain_turn(event, active_profile):
                yield result
            event.stop_event()
            return
        outcome = await self.dialogue.dispatch_event(event, {})
        if (
            str(getattr(event, "_plana_native_tool_profile", "") or "")
            in DOMAIN_PLUGINS.profiles()
            and not getattr(event, "_plana_domain_handler_executed", False)
        ):
            fallback_profile = str(
                getattr(event, "_plana_native_tool_profile", "") or ""
            )
            fallback_descriptor = DOMAIN_PLUGINS.for_profile(fallback_profile)
            if fallback_descriptor is not None and fallback_descriptor.direct_dispatch:
                setattr(event, "_plana_anchor_outbound", True)
                async for result in self._execute_domain_turn(event, fallback_profile):
                    yield result
                event.stop_event()
                return
        if outcome.reply:
            setattr(event, "_plana_anchor_outbound", True)
            if outcome.render_document:
                yield await render_dialogue_result(self.context, event, outcome.render_document, outcome.reply)
            else:
                yield event.plain_result(outcome.reply)
            if outcome.stop_event:
                event.stop_event()
        elif outcome.stop_event:
            logger.warning(
                "Plana dialogue requested stop without reply; letting AstrBot continue: reason=%s",
                outcome.reason,
            )

    def _prepare_native_turn(self, event: AstrMessageEvent) -> str:
        self._refresh_domain_plugins()
        text = event.get_message_str()
        current_profile = tool_profile_for_text(text)
        discussion = looks_like_service_discussion_request(text)
        pending_action_check = getattr(
            getattr(self, "dialogue", None),
            "has_pending_task_action",
            None,
        )
        pending_task_action = bool(
            callable(pending_action_check) and pending_action_check(event, text)
        )
        resumed = False
        if current_profile in DOMAIN_TOOL_PROFILES:
            profile = current_profile
        elif not pending_task_action and not discussion and self._resume_recent_tool_profile(event, text):
            resumed = True
            profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
        else:
            profile = current_profile
        if profile and not resumed:
            setattr(event, "_plana_native_tool_profile", profile)
        if profile in {
            "search",
            "service_query",
            "ani_plugin",
            "ncqq_plugin",
            "komga_plugin",
        }:
            event.set_extra("enable_streaming", False)
        if profile == "search" and not getattr(event, "_plana_turn_id", ""):
            setattr(event, "_plana_turn_id", uuid.uuid4().hex)
        return profile

    async def _execute_native_search_turn(self, event: AstrMessageEvent) -> None:
        tool = PlanaNativeSearchTool(self)
        query = search_query_from_message(event.get_message_str())
        logger.info(
            "Plana turn route: turn=%s profile=search tools=%s direct=true",
            getattr(event, "_plana_turn_id", ""),
            [tool.name],
        )
        await self._handle_using_llm_tool(event, tool, {"query": query})
        try:
            await tool.call(None, query=query, event=event)
        finally:
            await self._handle_llm_tool_respond(event, tool, {"query": query}, None)

    async def _handle_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        self._mark_provider_request_origin(event)

    async def _handle_llm_request(self, event: AstrMessageEvent, request_obj) -> None:
        if not self._should_process_llm_hook(event, request_obj):
            setattr(event, "_plana_llm_hook_managed", False)
            return
        setattr(event, "_plana_llm_hook_managed", True)
        if not getattr(event, "_plana_turn_id", ""):
            setattr(event, "_plana_turn_id", uuid.uuid4().hex)
        provider = self.context.get_using_provider()
        await self.dialogue.inject_prompt(event, request_obj, provider)
        profile = str(getattr(event, "_plana_native_tool_profile", "") or "chat")
        if profile in {
            "search",
            "service_query",
            "ani_plugin",
            "ncqq_plugin",
            "komga_plugin",
        }:
            event.set_extra("enable_streaming", False)
        tools = [
            str(getattr(tool, "name", "") or "")
            for tool in list(getattr(getattr(request_obj, "func_tool", None), "tools", []) or [])
            if str(getattr(tool, "name", "") or "")
        ]
        logger.info(
            "Plana turn route: turn=%s profile=%s tools=%s",
            getattr(event, "_plana_turn_id", ""),
            profile,
            tools,
        )

    async def _handle_llm_response(self, event: AstrMessageEvent, response) -> None:
        if getattr(event, "_plana_llm_hook_managed", None) is False:
            return
        if not self._should_process_llm_hook(event, None):
            return
        setattr(event, "_plana_anchor_outbound", True)
        self._suppress_domain_tool_narration(event, response)
        self._suppress_search_tool_narration(event, response)
        await self._finalize_native_search_response(event, response)
        self._append_service_artifacts(event, response)
        provider = self.context.get_using_provider()
        await self.dialogue.observe_response(event, response, provider)
        self._prepare_gallery_reaction(event, response)

    async def _handle_after_message_sent(self, event: AstrMessageEvent) -> None:
        self._remember_recent_tool_profile(event)
        self.dialogue.wake_state.observe_response(self.runtime, event, replied=True)
        storage = getattr(self.runtime, "storage", None)
        store = getattr(storage, "message_anchors", None)
        if store is not None:
            try:
                register_sent_message_anchors(
                    event,
                    runtime=self.runtime,
                    store=store,
                    session_store=self.dialogue.task_broker.sessions,
                )
            except Exception:  # noqa: BLE001
                logger.warning("Plana message anchor registration failed", exc_info=True)
        await super()._handle_after_message_sent(event)

    def _suppress_search_tool_narration(
        self,
        event: AstrMessageEvent,
        response: object,
    ) -> bool:
        profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
        raw_names = getattr(response, "tools_call_name", None)
        if isinstance(raw_names, str):
            tool_names = {raw_names}
        else:
            tool_names = {str(name) for name in list(raw_names or [])}
        if profile != "search" or "web_search_searxng" not in tool_names:
            return False
        setattr(response, "completion_text", "")
        setattr(response, "reasoning_content", "")
        setattr(response, "result_chain", None)
        logger.info(
            "Plana search tool narration suppressed: turn=%s tool=web_search_searxng",
            getattr(event, "_plana_turn_id", ""),
        )
        return True

    def _append_service_artifacts(self, event: AstrMessageEvent, response: object) -> None:
        artifacts = getattr(event, "_plana_service_artifacts", None)
        if not isinstance(artifacts, list) or not artifacts:
            return
        chain = getattr(response, "result_chain", None)
        if chain is None:
            from astrbot.core.message.message_event_result import MessageChain

            chain = MessageChain().message(str(getattr(response, "completion_text", "") or ""))
            setattr(response, "result_chain", chain)
        appended = 0
        for item in artifacts[:2]:
            path = str(item.get("path") or "") if isinstance(item, dict) else ""
            if path and Path(path).is_file():
                chain.file_image(path)
                appended += 1
        logger.info("Plana service artifacts appended: count=%s", appended)

    async def _finalize_native_search_response(
        self,
        event: AstrMessageEvent,
        response: object,
    ) -> None:
        if bool(getattr(event, "_plana_search_direct_delivery", False)):
            return
        result = getattr(event, "_plana_search_result", None)
        if not isinstance(result, dict):
            return
        text = finalize_search_response(
            str(getattr(response, "completion_text", "") or ""),
            result,
        )
        setattr(response, "completion_text", text)
        from astrbot.core.message.message_event_result import MessageChain

        chain = MessageChain().message(text)
        setattr(response, "result_chain", chain)
        document = recommendation_document(
            event.get_message_str(),
            text,
            search_result=result,
        )
        rendered = False
        if document is not None:
            try:
                path = await render_document_to_file(document)
                chain.file_image(path)
                rendered = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Plana recommendation card skipped: %s", exc)
        components = [
            str(getattr(getattr(item, "type", None), "value", getattr(item, "type", "")))
            for item in list(getattr(chain, "chain", []) or [])
        ]
        logger.info(
            "Plana search delivery: turn=%s status=%s attempts=%s sources=%s rendered=%s components=%s",
            getattr(event, "_plana_turn_id", ""),
            result.get("status"),
            result.get("attempts"),
            len(result.get("items", [])),
            rendered,
            components or ["text"],
        )

    async def _handle_using_llm_tool(self, event: AstrMessageEvent, tool, tool_args) -> None:
        profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
        tool_name = str(getattr(tool, "name", "") or getattr(tool, "__name__", ""))
        get_message = getattr(event, "get_message_str", None)
        message_text = str(get_message() or "") if callable(get_message) else ""
        if normalize_domain_tool_arguments(
            profile,
            tool_name,
            message_text,
            tool_args,
        ):
            call_count = int(getattr(event, "_plana_domain_tool_call_count", 0) or 0) + 1
            setattr(event, "_plana_domain_tool_call_count", call_count)
            logger.info(
                "Plana domain tool arguments normalized: profile=%s tool=%s call=%s",
                profile,
                tool_name,
                call_count,
            )
            if call_count > 1:
                logger.warning(
                    "Plana domain tool called repeatedly in one turn: profile=%s tool=%s call=%s",
                    profile,
                    tool_name,
                    call_count,
                )
        if not bool(self.config.get("assistant_task_progress_enabled", True)):
            return
        if bool(getattr(event, "_plana_tool_progress_sent", False)):
            return
        try:
            threshold = max(1, int(self.config.get("assistant_tool_progress_threshold_seconds", 8)))
        except (TypeError, ValueError):
            threshold = 8
        key = self._tool_progress_key(event, tool)
        old_task = self._tool_progress_tasks.pop(key, None)
        if old_task is not None:
            old_task.cancel()
        self._tool_progress_tasks[key] = asyncio.create_task(
            self._delayed_tool_progress(event, key, threshold)
        )

    async def _handle_llm_tool_respond(self, event: AstrMessageEvent, tool, tool_args, tool_result) -> None:
        _ = tool_args, tool_result
        task = self._tool_progress_tasks.pop(self._tool_progress_key(event, tool), None)
        if task is not None:
            task.cancel()

    def _tool_progress_key(self, event: AstrMessageEvent, tool: object) -> str:
        name = str(getattr(tool, "name", "") or getattr(tool, "__name__", "tool"))
        return f"{getattr(event, 'unified_msg_origin', 'global')}:{id(event)}:{name}"

    async def _delayed_tool_progress(self, event: AstrMessageEvent, key: str, threshold: int) -> None:
        try:
            await asyncio.sleep(threshold)
            if key not in self._tool_progress_tasks or self._terminating:
                return
            if bool(getattr(event, "_plana_tool_progress_sent", False)):
                return
            setattr(event, "_plana_tool_progress_sent", True)
            from astrbot.core.message.message_event_result import MessageChain

            await event.send(MessageChain().message("我还在处理，完成后直接把结果发给你。"))
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            logger.debug("Plana delayed tool progress skipped", exc_info=True)

    def _resend_artifact_result(self, event: AstrMessageEvent):
        if not is_artifact_resend_request(event.get_message_str()):
            return None
        scope_id, actor_id = self._conversation_identity(event)
        state = self.dialogue.task_broker.sessions.session(scope_id, actor_id)
        artifact_ref = dict(state.latest_artifact_ref or {})
        expires_at = int(artifact_ref.get("expires_at") or 0)
        if expires_at and expires_at <= int(__import__("time").time()):
            return event.plain_result("之前的图片或文件已经过期，我可以重新获取一次。")
        recipients = {str(item) for item in artifact_ref.get("authorized_recipients", [])}
        if recipients and actor_id not in recipients:
            return event.plain_result("这个文件不在你的授权接收范围内。")
        path = str(state.latest_artifact_path or "")
        if not path or not Path(path).is_file():
            return event.plain_result("之前的图片或文件已不可用，我可以重新获取一次。")
        logger.info("Plana artifact resent: scope=%s actor=%s", scope_id, actor_id)
        return event.make_result().file_image(path)

    def _conversation_identity(self, event: AstrMessageEvent) -> tuple[str, str]:
        scope_id = str(self.runtime.resolve_scope(event.unified_msg_origin) or "global")
        try:
            actor_id = str(self.runtime.identity_from_event(event).global_user_id or "user")
        except Exception:  # noqa: BLE001
            actor_id = str(event.get_sender_id() or "user")
        return scope_id, actor_id

    def _should_process_llm_hook(
        self,
        event: AstrMessageEvent,
        request_obj: object | None,
    ) -> bool:
        if self._terminating:
            return False
        if bool(getattr(event, "_plana_provider_request_preexisting", False)):
            return False
        return True

    def _mark_provider_request_origin(self, event: AstrMessageEvent) -> None:
        setattr(
            event,
            "_plana_provider_request_preexisting",
            self._event_provider_request(event) is not None,
        )

    def _event_provider_request(self, event: AstrMessageEvent) -> object | None:
        getter = getattr(event, "get_extra", None)
        if not callable(getter):
            return None
        try:
            return getter("provider_request")
        except Exception:  # noqa: BLE001
            return None
