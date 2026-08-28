from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from .actions import TURN_ACTIONS
from .models import DialogueDecision
from .wake import WakeDecision


@dataclass(frozen=True, slots=True)
class PreflightDecision:
    should_respond: bool
    reason: str
    source: str = "local"
    action_name: str = ""


class DialogueResponsePreflight:
    """Optional gate and controlled intent hint for configured preflight models."""

    _DIRECT_TOKENS = (
        "帮我",
        "请",
        "需要你",
        "你能",
        "你可以",
        "你来",
        "怎么看",
        "如何",
        "为什么",
        "怎么",
        "吗",
        "？",
        "?",
        "please",
        "can you",
        "could you",
        "tell me",
        "show me",
        "help me",
    )
    _MENTION_ONLY_TOKENS = (
        "名字",
        "名称",
        "提到",
        "说到",
        "叫 plana",
        "called plana",
        "name plana",
        "这个 plana",
        "plana 这个",
    )

    _LOCAL_ACTIONS = {action.name: action for action in TURN_ACTIONS}
    _LOCAL_INTENTS = {action.intent: action.name for action in TURN_ACTIONS}
    _CONTROL_ACTIONS = frozenset((*_LOCAL_ACTIONS, "chat", "ignore"))

    async def decide(
        self,
        runtime: Any,
        text: str,
        wake: WakeDecision,
        decision: DialogueDecision,
        provider: Any,
    ) -> PreflightDecision:
        if decision.route in {
            "reject",
            "memory_write",
            "status_query",
            "read_direct",
        }:
            return PreflightDecision(
                True,
                f"explicit_{decision.route}",
                action_name=str(decision.intent or ""),
            )
        if not bool(runtime.config.get("dialogue_response_preflight_enabled", True)):
            return self._local_fallback(text, wake, "disabled")
        timeout = self._timeout(runtime)
        model_provider = self._provider_for_preflight(provider)
        if model_provider is not None and hasattr(model_provider, "text_chat"):
            model_decision = await self._with_model(
                model_provider,
                text,
                wake,
                timeout,
            )
            if model_decision is not None:
                return model_decision
        return self._local_fallback(text, wake, "model_unavailable")

    def _provider_for_preflight(self, providers: Any) -> Any:
        if isinstance(providers, dict):
            return providers.get("preflight")
        return None

    async def _with_model(
        self,
        provider: Any,
        text: str,
        wake: WakeDecision,
        timeout: float,
    ) -> PreflightDecision | None:
        actions = ", ".join(sorted(self._CONTROL_ACTIONS))
        prompt = (
            "Decide whether Plana should answer this chat turn.\n"
            "Return strict JSON only: "
            "{\"respond\": true|false, \"action\": \"...\", \"reason\": \"...\"}.\n"
            "Respond true only when the speaker is directly asking or instructing Plana, "
            "or the message contains a clear actionable request for Plana.\n"
            "Respond false for third-person discussion, quoting, name-only mentions, "
            "casual mentions, or statements that do not ask Plana to do anything.\n"
            "Choose action only from this controlled list; do not invent actions: "
            f"{actions}.\n"
            "Use ignore when Plana should not answer. Use chat for ordinary dialogue. "
            "Use read/write actions only when the message clearly asks for that capability.\n"
            "Use a controlled task action only when the speaker clearly asks Plana to "
            "perform a concrete operation.\n"
            f"Wake source: {wake.source}\n"
            f"Message: {text[:600]}"
        )
        try:
            response = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt,
                    system_prompt=(
                        "You are a fast Plana response and intent gate. "
                        "Classify only whether to answer and which controlled action applies. "
                        "Return JSON only."
                    ),
                ),
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001
            return None
        raw = str(getattr(response, "completion_text", "") or "").strip()
        payload = self._parse_json(raw)
        if not isinstance(payload, dict):
            return None
        if "respond" not in payload:
            return None
        action_name = self._normalize_action(payload.get("action") or payload.get("intent"))
        should_respond = bool(payload.get("respond"))
        if action_name == "ignore":
            should_respond = False
        if should_respond and not action_name:
            action_name = "chat"
        return PreflightDecision(
            should_respond,
            str(payload.get("reason") or "model_gate")[:120],
            "model",
            action_name=action_name,
        )

    def _local_fallback(
        self,
        text: str,
        wake: WakeDecision,
        reason: str,
    ) -> PreflightDecision:
        lowered = text.lower()
        if any(token in lowered for token in self._MENTION_ONLY_TOKENS):
            return PreflightDecision(False, f"{reason}:mention_only", action_name="ignore")
        if wake.source in {"astrbot_at_or_wake", "private_chat"}:
            return PreflightDecision(True, f"{reason}:direct_channel", action_name="chat")
        if any(token in lowered for token in self._DIRECT_TOKENS):
            return PreflightDecision(True, f"{reason}:direct_language", action_name="chat")
        return PreflightDecision(False, f"{reason}:ambiguous_mention", action_name="ignore")

    def _normalize_action(self, raw: object) -> str:
        action = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not action:
            return ""
        if action in {"none", "no_reply", "do_not_respond", "silent"}:
            return "ignore"
        if action in self._LOCAL_ACTIONS or action in {"chat", "ignore"}:
            return action
        return self._LOCAL_INTENTS.get(action, "")

    def _timeout(self, runtime: Any) -> float:
        try:
            seconds = float(runtime.config.get("dialogue_response_preflight_timeout_seconds", 1.2))
        except (TypeError, ValueError):
            seconds = 1.2
        return max(0.2, min(seconds, 5.0))

    def _parse_json(self, raw: str) -> Any:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
