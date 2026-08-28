from __future__ import annotations

from dataclasses import replace
import json
import re
from typing import Any

from ..utils.intent_patterns import looks_like_informational_document_request
from .delivery import reply_message_id_from_event
from .preflight import PreflightDecision
from .wake import WakeDecision


class DialogueServiceSupportMixin:
    def turn_context(self, event: Any) -> dict[str, object]:
        wake = self._wake_decision(event)
        context, _decision = self.router.decision_for_event(self.runtime, event, wake)
        return context.to_dict()

    def _wake_decision(self, event: Any) -> WakeDecision:
        cached = getattr(event, "_plana_wake_decision", None)
        if isinstance(cached, WakeDecision):
            return cached
        scope_id, actor_id = self._conversation_identity(event)
        session_state = self.task_broker.sessions.session(scope_id, actor_id)
        anchor_resolution = self._resolve_reply_anchor(event, scope_id, actor_id)
        return self.wake_state.decide(
            self.runtime,
            event,
            session_state=session_state,
            anchor_resolution=anchor_resolution,
        )

    def _resolve_reply_anchor(
        self,
        event: Any,
        scope_id: str,
        actor_id: str,
    ) -> Any | None:
        cached = getattr(event, "_plana_message_anchor_resolution", None)
        if cached is not None:
            return cached
        reply_message_id = reply_message_id_from_event(event)
        if not reply_message_id:
            return None
        storage = getattr(self.runtime, "storage", None)
        store = getattr(storage, "message_anchors", None)
        resolver = getattr(store, "resolve_reply", None)
        if not callable(resolver):
            return None
        try:
            resolution = resolver(scope_id, reply_message_id, actor_id)
        except Exception:  # noqa: BLE001
            return None
        if resolution is None:
            return None
        setattr(event, "_plana_message_anchor_resolution", resolution)
        return resolution

    def _message_anchor_prompt(self, event: Any) -> str:
        resolution = getattr(event, "_plana_message_anchor_resolution", None)
        if resolution is None:
            return ""
        projection = getattr(resolution, "public_projection", {})
        if not isinstance(projection, dict):
            projection = {}
        public_json = json.dumps(
            projection,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if bool(getattr(resolution, "is_owner", False)):
            return (
                "[Plana message anchor]\n"
                "The user replied to Plana's own earlier message and is the same actor. "
                "Continue only from this actor's current TaskSession state; never recreate "
                "expired state from the anchor. Public result context: "
                f"{public_json}"
            )
        return (
            "[Plana public reply fork]\n"
            "The user replied to another actor's Plana message. Treat this as a new, "
            "actor-scoped read-only branch. Do not inherit task IDs, pending actions, "
            "confirmation rights, cancellation rights, credentials, or private state. "
            f"Only this public result context may be referenced: {public_json}"
        )

    def _auto_turn_analysis_enabled(self) -> bool:
        return bool(self.runtime.config.get("assistant_task_enabled", True))

    def _looks_like_plana_command(self, text: str) -> bool:
        lowered = " ".join(str(text or "").strip().lower().split())
        command_prefixes = (
            "plana status",
            "plana mode",
            "plana search",
            "plana remember",
            "plana do",
            "plana help",
        )
        return any(
            lowered == prefix or lowered.startswith(prefix + " ")
            for prefix in command_prefixes
        )

    def _should_dispatch_event(self, event: Any, wake: WakeDecision) -> bool:
        if (
            self._is_group_event(event)
            and wake.state == "observation"
            and not wake.should_dispatch
        ):
            return False
        if wake.should_dispatch:
            return True
        if bool(getattr(event, "call_llm", False)):
            return True
        if bool(getattr(event, "is_at_or_wake_command", False)):
            return True
        is_private = getattr(event, "is_private_chat", None)
        if callable(is_private):
            try:
                return bool(is_private())
            except Exception:  # noqa: BLE001
                return False
        message_type = event.get_message_type()
        normalized = str(getattr(message_type, "value", message_type))
        return "FriendMessage" in normalized or "FRIEND" in normalized

    async def _preflight_allows(
        self,
        event: Any,
        text: str,
        wake: WakeDecision,
        decision: Any,
        provider: Any,
    ) -> PreflightDecision:
        if not self._requires_preflight(event, wake, decision, provider):
            return PreflightDecision(True, "not_required")
        cached = getattr(event, "_plana_preflight_accepted", None)
        if cached is not None:
            return PreflightDecision(bool(cached), "cached", "cache")
        return await self.preflight.decide(self.runtime, text, wake, decision, provider)

    def _requires_preflight(
        self,
        event: Any,
        wake: WakeDecision,
        decision: Any,
        provider: Any,
    ) -> bool:
        if (
            decision.intent == "tool_execution_candidate"
            and bool(self.runtime.config.get("assistant_native_tool_mode", True))
        ):
            return False
        if decision.route in {
            "reject",
            "memory_write",
            "status_query",
            "read_direct",
        }:
            return False
        if not self._preflight_model_enabled(provider):
            return False
        if self._configured_chat_preflight(provider):
            return decision.route == "inject_prompt"
        if not self._is_group_event(event):
            return False
        if wake.source in {"plana_name_mention", "astrbot_wake"}:
            return True
        return bool(getattr(event, "call_llm", False)) and wake.source == "astrbot_message"

    def _configured_chat_preflight(self, provider: Any) -> bool:
        return bool(
            self.runtime.config.get("dialogue_preflight_classify_chat_turns", False)
        ) and self._preflight_model_enabled(provider)

    def _preflight_model_enabled(self, provider: Any) -> bool:
        if not bool(self.runtime.config.get("dialogue_response_preflight_enabled", False)):
            return False
        return isinstance(provider, dict) and provider.get("preflight") is not None

    def _is_group_event(self, event: Any) -> bool:
        is_private = getattr(event, "is_private_chat", None)
        if callable(is_private):
            try:
                return not bool(is_private())
            except Exception:  # noqa: BLE001
                pass
        try:
            message_type = event.get_message_type()
        except Exception:  # noqa: BLE001
            return False
        normalized = str(getattr(message_type, "value", message_type))
        return "GroupMessage" in normalized or "GROUP" in normalized

    def _apply_preflight_intent(
        self,
        text: str,
        turn_context: Any,
        decision: Any,
        preflight: PreflightDecision,
    ) -> tuple[Any, Any]:
        if looks_like_informational_document_request(text):
            if decision.intent == "chat":
                return turn_context, decision
            informational = self.router.decision_for_action(
                "chat",
                text,
                reason="informational_document_request",
            )
            if informational is None:
                return turn_context, decision
            return (
                replace(
                    turn_context,
                    route=informational.route,
                    intent=informational.intent,
                    reason=informational.reason,
                    proposal_source=informational.proposal_source,
                ),
                informational,
            )
        if preflight.source != "model" or not preflight.action_name:
            return turn_context, decision
        hinted = self.router.decision_for_action(
            preflight.action_name,
            text,
            reason=f"preflight_model:{preflight.reason}",
        )
        if hinted is None:
            return turn_context, decision
        return (
            replace(
                turn_context,
                route=hinted.route,
                intent=hinted.intent,
                reason=hinted.reason,
                proposal_source=hinted.proposal_source,
            ),
            hinted,
        )

    def _user_status_text(self) -> str:
        formatter = getattr(self.runtime, "user_status_text", None)
        if callable(formatter):
            return str(formatter())
        return "我在线，可以聊天、检索记忆，并在需要时处理受控任务。详细诊断请使用 /plana status。"

    def _remember_basic_text(self, event: Any, text: str) -> str:
        content = self._basic_memory_content(text)
        if not content:
            return "没有可记住的内容。"
        remember = getattr(self.runtime, "remember_text", None)
        if not callable(remember):
            return "当前记忆功能不可用。"
        result = str(remember(event, content) or "")
        if result.endswith(": empty"):
            return "没有可记住的内容。"
        if result.endswith(": stored"):
            return "已记住。"
        return result or "已记住。"

    def _basic_memory_content(self, text: str) -> str:
        clean = " ".join(str(text or "").strip().split())
        clean = re.sub(r"^(plana|普拉娜|普拉纳)[，,。！!\s]*", "", clean, flags=re.IGNORECASE)
        prefixes = (
            "请你记住",
            "请记住",
            "帮我记住",
            "帮我记",
            "记住一下",
            "记住",
            "保存到记忆",
            "写入记忆",
            "加入记忆",
            "remember this",
            "save memory",
            "write memory",
        )
        lowered = clean.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix.lower()):
                clean = clean[len(prefix):].strip(" ：:，,。 ")
                break
        return clean[:1000]

    def _record_direct_response(self, event: Any, text: str) -> None:
        if not str(text or "").strip():
            return
        self.ledger.ingest_response(self.runtime, event, text)
        self.wake_state.observe_response(self.runtime, event, replied=True)

    def _conversation_identity(self, event: Any) -> tuple[str, str]:
        scope_id = str(self.runtime.resolve_scope(event.unified_msg_origin) or "global")
        try:
            actor_id = str(self.runtime.identity_from_event(event).global_user_id or "user")
        except Exception:  # noqa: BLE001
            try:
                actor_id = str(event.get_sender_id() or "user")
            except Exception:  # noqa: BLE001
                actor_id = "user"
        return scope_id, actor_id

    def _append_temp_user_context(self, request_obj: Any, prompt_block: str) -> bool:
        parts = getattr(request_obj, "extra_user_content_parts", None)
        if parts is None:
            if not hasattr(request_obj, "extra_user_content_parts"):
                return False
            parts = []
            setattr(request_obj, "extra_user_content_parts", parts)
        try:
            from astrbot.core.agent.message import TextPart
        except Exception:  # noqa: BLE001
            return False
        try:
            part = TextPart(text=prompt_block)
            mark_as_temp = getattr(part, "mark_as_temp", None)
            if callable(mark_as_temp):
                marked = mark_as_temp()
                if marked is not None:
                    part = marked
            parts.append(part)
        except Exception:  # noqa: BLE001
            return False
        return True
