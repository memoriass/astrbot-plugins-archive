from __future__ import annotations

from dataclasses import replace

from .actions import TURN_ACTIONS, TurnAction
from .models import DialogueDecision


class DialogueTurnAnalyzer:
    """Rule-first turn analyzer owned by Plana Core.

    Models and sibling centers may advise later stages, but the first routing
    decision stays local and only emits controlled branches.
    """

    def __init__(self, actions: tuple[TurnAction, ...] = TURN_ACTIONS) -> None:
        self.actions = actions
        self._actions_by_name = {action.name: action for action in actions}
        actions_by_intent: dict[str, TurnAction] = {}
        ambiguous_intents: set[str] = set()
        for action in actions:
            if action.intent in actions_by_intent:
                ambiguous_intents.add(action.intent)
                actions_by_intent.pop(action.intent, None)
                continue
            if action.intent not in ambiguous_intents:
                actions_by_intent[action.intent] = action
        self._actions_by_intent = actions_by_intent
        self._ambiguous_intents = frozenset(ambiguous_intents)

    def analyze(
        self,
        text: str,
        source: str = "astrbot_message",
        *,
        message_type: str = "",
        is_wake: bool = False,
    ) -> DialogueDecision:
        clean = " ".join(text.strip().split())
        lowered = clean.lower()
        if not clean:
            return self._chat("empty_turn")
        if source in {"llm_tool", "web_admin"}:
            return DialogueDecision(
                "codex_candidate",
                codex_candidate=True,
                intent="tool_execution_candidate",
                intent_text=clean,
                proposal_source=source,
                reason=f"controlled_execution_{source}",
            )
        for action in self.actions:
            if action.matches(lowered):
                return action.to_decision(clean)
        return self._chat("normal_dialogue_prompt_context")

    def action_catalog(self) -> list[dict[str, object]]:
        return [
            {
                "name": action.name,
                "intent": action.intent,
                "route": action.route,
                "proposal_source": action.proposal_source,
                "codex_candidate": action.codex_candidate,
                "should_stop_event": action.should_stop_event,
            }
            for action in self.actions
        ]

    def decision_for_action(
        self,
        action_name: str,
        text: str,
        *,
        reason: str = "",
    ) -> DialogueDecision | None:
        normalized = action_name.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"", "ignore"}:
            return None
        if normalized == "chat":
            return self._chat(reason or "preflight_chat_intent")
        action = self._actions_by_name.get(normalized)
        if action is not None:
            decision = action.to_decision(" ".join(text.strip().split()))
            if reason:
                return replace(decision, reason=reason)
            return decision
        if normalized in self._ambiguous_intents:
            return None
        action = self._actions_by_intent.get(normalized)
        if action is None:
            return None
        decision = action.to_decision(" ".join(text.strip().split()))
        if reason:
            return replace(decision, reason=reason)
        return decision

    def _chat(self, reason: str) -> DialogueDecision:
        return DialogueDecision(
            "inject_prompt",
            should_inject_prompt=True,
            intent="chat",
            reason=reason,
        )
