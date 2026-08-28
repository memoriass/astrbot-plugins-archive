from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any

from .continuation import assess_group_continuation


@dataclass(frozen=True, slots=True)
class WakeDecision:
    state: str
    source: str
    reason: str
    is_wake: bool = False
    should_dispatch: bool = False
    direct_reply: str = ""


@dataclass(slots=True)
class _WakeSession:
    state: str
    expires_at: float
    last_reason: str
    responded_at: float = 0.0


class DialogueWakeStateMachine:
    """Local wake/familiarity gate for AstrBot message events."""

    DEFAULT_WAKE_WORDS = ("plana", "普拉娜", "普拉纳")
    POKE_MARKERS = (
        "poke",
        "nudge",
        "戳一戳",
        "戳了戳",
        "拍一拍",
        "PokeMessage",
        "PokeNotify",
    )

    def __init__(self) -> None:
        self._sessions: dict[object, _WakeSession] = {}
        self._session_origins: dict[tuple[str, ...], str] = {}

    def decide(
        self,
        runtime: Any,
        event: Any,
        *,
        session_state: Any | None = None,
        anchor_resolution: Any | None = None,
    ) -> WakeDecision:
        cached = getattr(event, "_plana_wake_decision", None)
        if isinstance(cached, WakeDecision):
            return cached
        decision = self._decide(
            runtime,
            event,
            session_state=session_state,
            anchor_resolution=anchor_resolution,
        )
        try:
            setattr(event, "_plana_wake_decision", decision)
        except Exception:  # noqa: BLE001
            pass
        return decision

    def _decide(
        self,
        runtime: Any,
        event: Any,
        *,
        session_state: Any | None,
        anchor_resolution: Any | None,
    ) -> WakeDecision:
        if not bool(runtime.config.get("enable_dialogue_wake_state", True)):
            return WakeDecision("disabled", "astrbot_message", "disabled")
        text = self._message_text(event)
        command_like = text.startswith("/")
        key = self._session_key(runtime, event)
        now = time()
        window = self._familiar_window(runtime)
        wake_words = self._wake_words(runtime)
        framework_at = bool(getattr(event, "is_at_or_wake_command", False))
        framework_wake = bool(getattr(event, "is_wake", False) and framework_at)
        poke = self._is_poke_event(event, text)
        name_mention = (
            not command_like
            and self._contains_wake_word(text, wake_words)
        )
        direct_private = not command_like and self._is_private(event)

        if command_like:
            return WakeDecision("command", "astrbot_message", "command")
        if poke:
            self._set_session(key, "summoned", now + window, "poke")
            return WakeDecision(
                "summoned",
                "plana_poke",
                "poke",
                is_wake=True,
                should_dispatch=True,
                direct_reply=self._poke_response(runtime),
            )
        if framework_wake or framework_at:
            reason = "astrbot_wake" if framework_wake else "astrbot_at_or_wake"
            self._set_session(key, "summoned", now + window, reason)
            return WakeDecision(
                "summoned",
                reason,
                reason,
                is_wake=True,
                should_dispatch=True,
            )
        if name_mention:
            self._set_session(key, "summoned", now + window, "wake_word")
            return WakeDecision(
                "mentioned",
                "plana_name_mention",
                "wake_word",
                is_wake=True,
                should_dispatch=True,
            )
        if direct_private:
            return WakeDecision(
                "observing",
                "private_chat",
                "private_chat",
                is_wake=True,
                should_dispatch=True,
            )
        if anchor_resolution is not None:
            continuation = assess_group_continuation(
                event,
                session_state,
                anchor_resolution=anchor_resolution,
                scope_id=key[1],
                actor_id=key[2],
                now=now,
                max_state_age_seconds=window,
            )
            if continuation.should_continue:
                return WakeDecision(
                    "anchored",
                    "plana_message_anchor",
                    continuation.reason,
                    is_wake=True,
                    should_dispatch=True,
                )
        session = self._sessions.get(key)
        if session and session.expires_at >= now:
            if session.state == "observation":
                if not self._is_private(event):
                    continuation = assess_group_continuation(
                        event,
                        session_state,
                        anchor_resolution=anchor_resolution,
                        scope_id=key[1],
                        actor_id=key[2],
                        now=now,
                        max_state_age_seconds=window,
                    )
                    if not continuation.should_continue:
                        return WakeDecision(
                            "observation",
                            "plana_observation",
                            continuation.reason,
                        )
                return WakeDecision(
                    "observation",
                    "plana_observation",
                    (
                        "group_continuation"
                        if not self._is_private(event)
                        else session.last_reason
                    ),
                    is_wake=True,
                    should_dispatch=True,
                )
            session.state = "familiar"
            session.expires_at = now + window
            return WakeDecision(
                "familiar",
                "plana_familiar",
                session.last_reason,
                is_wake=True,
                should_dispatch=True,
            )
        if session:
            self._sessions.pop(key, None)
            origin = self._session_origins.pop(key, key[1])
            if self._sessions.get(origin) is session:
                self._sessions.pop(origin, None)
        return WakeDecision("not_present", "astrbot_message", "no_wake_signal")

    def observe_response(self, runtime: Any, event: Any, *, replied: bool = True) -> None:
        """Keep a short post-response observation window for natural follow-ups."""

        if not replied or not bool(runtime.config.get("enable_dialogue_wake_state", True)):
            return
        key = self._session_key(runtime, event)
        now = time()
        expires_at = now + self._observation_window(runtime)
        session = self._sessions.get(key)
        if session:
            session.state = "observation"
            session.last_reason = "response_observation"
            session.responded_at = now
            if session.expires_at < expires_at:
                session.expires_at = expires_at
            return
        self._store_session(
            key,
            _WakeSession(
                "observation",
                expires_at,
                "response_observation",
                responded_at=now,
            ),
        )

    def _set_session(
        self,
        key: tuple[str, ...],
        state: str,
        expires_at: float,
        reason: str,
    ) -> None:
        self._store_session(key, _WakeSession(state, expires_at, reason))

    def _store_session(
        self,
        key: tuple[str, ...],
        session: _WakeSession,
    ) -> None:
        self._sessions[key] = session
        self._sessions[self._session_origins.get(key, key[1])] = session

    def _wake_words(self, runtime: Any) -> tuple[str, ...]:
        raw = str(runtime.config.get("dialogue_wake_words", "") or "").strip()
        if not raw:
            return self.DEFAULT_WAKE_WORDS
        words = tuple(
            item.strip()
            for item in raw.replace(";", ",").split(",")
            if item.strip()
        )
        return words or self.DEFAULT_WAKE_WORDS

    def _familiar_window(self, runtime: Any) -> int:
        try:
            seconds = int(runtime.config.get("dialogue_familiar_window_seconds", 180))
        except (TypeError, ValueError):
            seconds = 180
        return max(15, min(seconds, 1800))

    def _observation_window(self, runtime: Any) -> int:
        try:
            seconds = int(runtime.config.get("dialogue_observation_window_seconds", 90))
        except (TypeError, ValueError):
            seconds = 90
        return max(10, min(seconds, 900))

    def _poke_response(self, runtime: Any) -> str:
        text = str(
            runtime.config.get("dialogue_poke_response", "我在，需要我处理什么？") or ""
        ).strip()
        return text or "我在，需要我处理什么？"

    def _contains_wake_word(self, text: str, wake_words: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(word.lower() in lowered for word in wake_words)

    def _is_poke_event(self, event: Any, text: str) -> bool:
        pieces = [text, str(getattr(event, "message_obj", ""))]
        try:
            message_type = event.get_message_type()
            pieces.append(str(getattr(message_type, "value", message_type)))
        except Exception:  # noqa: BLE001
            pass
        pieces.extend(
            str(getattr(event, name, ""))
            for name in ("type", "event_type", "message_type", "sub_type")
        )
        haystack = " ".join(piece for piece in pieces if piece)
        lowered = haystack.lower()
        return any(marker.lower() in lowered for marker in self.POKE_MARKERS)

    def _is_private(self, event: Any) -> bool:
        private = getattr(event, "is_private_chat", None)
        if callable(private):
            try:
                return bool(private())
            except Exception:  # noqa: BLE001
                return False
        try:
            message_type = event.get_message_type()
        except Exception:  # noqa: BLE001
            return False
        normalized = str(getattr(message_type, "value", message_type))
        return "FriendMessage" in normalized or "FRIEND" in normalized

    def _message_text(self, event: Any) -> str:
        try:
            return str(event.get_message_str() or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _session_key(self, runtime: Any, event: Any) -> tuple[str, ...]:
        origin = str(getattr(event, "unified_msg_origin", "") or "global")
        if self._is_private(event):
            key = ("private", origin)
            self._session_origins[key] = origin
            return key
        try:
            scope_id = str(runtime.resolve_scope(origin) or origin)
        except Exception:  # noqa: BLE001
            scope_id = origin
        try:
            actor_id = str(runtime.identity_from_event(event).global_user_id or "user")
        except Exception:  # noqa: BLE001
            try:
                actor_id = str(event.get_sender_id() or "user")
            except Exception:  # noqa: BLE001
                actor_id = "user"
        key = ("group", scope_id, actor_id)
        self._session_origins[key] = origin
        return key
