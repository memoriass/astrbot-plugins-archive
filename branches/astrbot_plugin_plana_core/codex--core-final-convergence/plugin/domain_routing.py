from __future__ import annotations

import inspect
from time import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..dialogue.domain_tool_route import (
    DOMAIN_TOOL_PROFILES,
    is_domain_followup_text,
)
from ..dialogue.domain_contracts import DOMAIN_PLUGINS


def _domain_response_item(event: AstrMessageEvent, item: object) -> object | None:
    if isinstance(item, str):
        text = item.strip()
        return event.plain_result(text) if text else None
    return item


class DomainRoutingMixin:
    def _refresh_domain_plugins(self) -> None:
        get_stars = getattr(self.context, "get_all_stars", None)
        if not callable(get_stars):
            return
        before = DOMAIN_PLUGINS.profiles()
        errors = DOMAIN_PLUGINS.discover(get_stars())
        after = DOMAIN_PLUGINS.profiles()
        signature = (after, tuple(errors))
        if signature == getattr(self, "_plana_domain_registry_signature", None):
            return
        setattr(self, "_plana_domain_registry_signature", signature)
        if before != after:
            logger.info("Plana domain harness registry refreshed: profiles=%s", sorted(after))
        for error in errors:
            logger.warning("Plana domain harness discovery skipped: %s", error)

    async def _execute_domain_turn(self, event: AstrMessageEvent, profile: str):
        setattr(event, "_plana_domain_handler_executed", True)
        self._refresh_domain_plugins()
        descriptor = DOMAIN_PLUGINS.for_profile(profile)
        if descriptor is None or not descriptor.direct_dispatch:
            return
        manager = self.context.get_llm_tool_manager()
        get_tool = getattr(manager, "get_func", None) or getattr(manager, "get_tool", None)
        tool = get_tool(descriptor.tool_name) if callable(get_tool) else None
        handler = getattr(tool, "handler", None)
        if (
            tool is None
            or not bool(getattr(tool, "active", True))
            or not callable(handler)
        ):
            yield event.plain_result(
                f"{descriptor.domain_id} 领域插件当前未启用，无法处理这条请求。"
            )
            return
        current_text = str(event.get_message_str() or "").strip()
        context_text = str(getattr(event, "_plana_domain_context_text", "") or "").strip()
        target = current_text
        if context_text and context_text != current_text:
            target = f"前文请求：{context_text}\n当前跟进：{current_text}"
        tool_args = descriptor.dispatch_arguments(target)
        logger.info(
            "Plana domain direct dispatch: domain=%s context=%s current=%s",
            descriptor.domain_id,
            bool(context_text),
            current_text[:80],
        )
        await self._handle_using_llm_tool(event, tool, tool_args)
        tool_args.clear()
        tool_args.update(descriptor.dispatch_arguments(target))
        handled = False
        failed = False
        try:
            ready = handler(event, **tool_args)
            if inspect.isasyncgen(ready):
                async for item in ready:
                    item = _domain_response_item(event, item)
                    if item is not None:
                        handled = True
                        yield item
            elif inspect.isawaitable(ready):
                item = _domain_response_item(event, await ready)
                if item is not None:
                    handled = True
                    yield item
            else:
                ready = _domain_response_item(event, ready)
            if not inspect.isasyncgen(ready) and not inspect.isawaitable(ready) and ready is not None:
                handled = True
                yield ready
        except Exception as exc:  # noqa: BLE001
            failed = True
            logger.error(
                "Plana domain direct dispatch failed: domain=%s",
                descriptor.domain_id,
                exc_info=True,
            )
            yield event.plain_result(f"{descriptor.domain_id} 请求执行失败：{exc}")
        finally:
            await self._handle_llm_tool_respond(event, tool, tool_args, None)
        if handled and not failed:
            setattr(event, "_plana_domain_profile_committed", True)
            self._remember_recent_tool_profile(event)

    def _remember_recent_tool_profile(self, event: AstrMessageEvent) -> None:
        if not getattr(event, "_plana_domain_profile_committed", False):
            return
        profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
        if profile not in DOMAIN_TOOL_PROFILES:
            return
        scope_id, actor_id = self._conversation_identity(event)
        recent = getattr(self, "_plana_recent_tool_profiles", None)
        if not isinstance(recent, dict):
            recent = {}
            setattr(self, "_plana_recent_tool_profiles", recent)
        now = time()
        for key, value in list(recent.items()):
            if float(value[1] or 0.0) < now:
                recent.pop(key, None)
        get_message = getattr(event, "get_message_str", None)
        current_text = str(get_message() or "").strip() if callable(get_message) else ""
        prior_context = str(getattr(event, "_plana_domain_context_text", "") or "").strip()
        context_text = prior_context or current_text
        if prior_context and current_text and current_text not in prior_context:
            context_text = (prior_context + "\n跟进补充：" + current_text)[-1200:]
        recent[(scope_id, actor_id)] = (profile, now + 600.0, context_text)
        logger.info(
            "Plana recent domain profile stored: scope=%s actor=%s profile=%s ttl=600",
            scope_id,
            actor_id,
            profile,
        )

    def _resume_recent_tool_profile(self, event: AstrMessageEvent, text: str) -> bool:
        if not is_domain_followup_text(text):
            return False
        scope_id, actor_id = self._conversation_identity(event)
        recent = getattr(self, "_plana_recent_tool_profiles", {})
        stored = recent.get((scope_id, actor_id), ("", 0.0, ""))
        profile = str(stored[0] or "") if len(stored) > 0 else ""
        expires_at = float(stored[1] or 0.0) if len(stored) > 1 else 0.0
        context_text = str(stored[2] or "") if len(stored) > 2 else ""
        if not profile or expires_at < time():
            return False
        setattr(event, "_plana_native_tool_profile", profile)
        if context_text:
            setattr(event, "_plana_domain_context_text", context_text)
        setattr(event, "is_at_or_wake_command", True)
        logger.info(
            "Plana recent domain profile resumed: scope=%s actor=%s profile=%s text=%s",
            scope_id,
            actor_id,
            profile,
            str(text or "")[:80],
        )
        return True

    def _suppress_domain_tool_narration(
        self,
        event: AstrMessageEvent,
        response: object,
    ) -> bool:
        profile = str(getattr(event, "_plana_native_tool_profile", "") or "")
        call_count = int(getattr(event, "_plana_domain_tool_call_count", 0) or 0)
        descriptor = DOMAIN_PLUGINS.for_profile(profile)
        if descriptor is None or not descriptor.direct_dispatch or call_count < 1:
            return False
        setattr(response, "completion_text", "")
        setattr(response, "reasoning_content", "")
        setattr(response, "result_chain", None)
        logger.info(
            "Plana domain post-tool narration suppressed: domain=%s turn=%s calls=%s",
            descriptor.domain_id,
            getattr(event, "_plana_turn_id", ""),
            call_count,
        )
        return True
