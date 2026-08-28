from __future__ import annotations

from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.event.filter import CustomFilter
except ModuleNotFoundError:  # pragma: no cover - used by standalone checks
    import logging

    logger = logging.getLogger(__name__)
    AstrMessageEvent = Any

    class CustomFilter:  # type: ignore[no-redef]
        def __init__(self, raise_error: bool = True, **_kwargs: Any) -> None:
            self.raise_error = raise_error


_ACTIVE_PLUGIN: Any = None

_DIRECTED_NAME_WAKE_TOKENS = (
    "帮我",
    "请",
    "需要你",
    "你能",
    "你可以",
    "你来",
    "你帮",
    "麻烦",
    "给我",
    "告诉我",
    "查一下",
    "看一下",
    "说一下",
    "搜一下",
    "总结一下",
    "处理一下",
    "分析一下",
    "检查一下",
    "please",
    "can you",
    "could you",
    "help me",
    "tell me",
    "show me",
)

_WAKE_START_ACTION_TOKENS = (
    *_DIRECTED_NAME_WAKE_TOKENS,
    "搜索",
    "检索",
    "回忆",
    "记住",
    "保存",
    "列出",
    "查看",
    "总结",
    "创建",
    "添加",
    "安排",
    "调用",
    "使用",
    "处理",
    "分析",
    "检查",
    "看看",
    "状态",
    "情况",
    "如何",
    "怎么",
    "为什么",
    "吗",
    "？",
    "?",
    "在吗",
    "在不在",
    "聊天",
    "聊聊",
    "search",
    "recall",
    "remember",
    "save",
    "list",
    "show",
    "check",
    "summarize",
    "create",
    "add",
    "use skill",
    "call skill",
    "invoke skill",
    "status",
    "workflow",
    "task",
    "todo",
    "memory",
    "history",
    "profile",
    "context",
)

_DIRECTED_AFTER_NAME_ACTION_TOKENS = (
    "搜索",
    "检索",
    "回忆",
    "记住",
    "保存",
    "列出",
    "查看",
    "总结",
    "创建",
    "添加",
    "安排",
    "调用",
    "使用",
    "处理",
    "分析",
    "检查",
    "看看",
    "search",
    "recall",
    "remember",
    "save",
    "list",
    "show",
    "check",
    "summarize",
    "create",
    "add",
    "use",
    "call",
    "invoke",
)

_MENTION_ONLY_TOKENS = (
    "名字",
    "名称",
    "提到",
    "说到",
    "叫 plana",
    "这个 plana",
    "plana 这个",
    "called plana",
    "name plana",
    "plana is only mentioned",
    "only mentioned as a name",
)


def set_active_plugin(plugin: Any) -> None:
    global _ACTIVE_PLUGIN
    _ACTIVE_PLUGIN = plugin


def get_active_plugin() -> Any:
    return _ACTIVE_PLUGIN


class PlanaPassiveObserveFilter(CustomFilter):
    """Record dialogue context without activating AstrBot's handler pipeline."""

    def filter(self, event: AstrMessageEvent, cfg: Any) -> bool:
        plugin = get_active_plugin()
        if (
            plugin is None
            or bool(getattr(plugin, "_terminating", False))
            or not bool(getattr(getattr(plugin, "runtime", None), "enabled", False))
        ):
            return False
        text = _message_text(event)
        if not text or _is_command_like(text):
            return False
        try:
            scheduler = getattr(plugin, "_schedule_passive_dialogue_observe", None)
            if callable(scheduler):
                scheduler(event)
            else:
                plugin.dialogue.observe_message(event)
        except Exception:  # noqa: BLE001
            logger.warning("Plana passive dialogue observe skipped", exc_info=True)
        return False


class PlanaActiveTurnFilter(CustomFilter):
    """Activate Plana only for turns it is allowed to consider handling."""

    def filter(self, event: AstrMessageEvent, cfg: Any) -> bool:
        plugin = get_active_plugin()
        if (
            plugin is None
            or bool(getattr(plugin, "_terminating", False))
            or not bool(getattr(getattr(plugin, "runtime", None), "enabled", False))
        ):
            return False
        text = _message_text(event)
        if not text and not _is_poke_event(event, text):
            return False
        if _is_command_like(text):
            return False
        if _is_poke_event(event, text):
            return True
        if bool(getattr(event, "is_at_or_wake_command", False)):
            return True
        if bool(getattr(event, "call_llm", False)):
            return True
        if _is_private(event):
            if _is_webchat(event):
                setattr(event, "is_at_or_wake_command", True)
            return True
        resume = getattr(plugin, "_resume_recent_tool_profile", None)
        if callable(resume) and resume(event, text):
            return True
        direct_name_wake = _is_direct_name_wake(text, _wake_words(plugin))
        if _looks_like_codex_work_request(text):
            logger.info(
                "Plana active filter Codex work request: direct_name_wake=%s webchat=%s",
                direct_name_wake,
                _is_webchat(event),
            )
            return True
        if direct_name_wake:
            return True
        consider = getattr(getattr(plugin, "dialogue", None), "should_consider_event", None)
        if callable(consider):
            try:
                return bool(consider(event))
            except Exception:  # noqa: BLE001
                logger.warning("Plana behavior opportunity check failed", exc_info=True)
        return False


def _wake_words(plugin: Any) -> tuple[str, ...]:
    runtime = getattr(plugin, "runtime", None)
    config = getattr(runtime, "config", {}) or {}
    raw = str(config.get("dialogue_wake_words", "") or "").strip()
    if not raw:
        return ("plana", "普拉娜", "普拉纳")
    words = tuple(
        item.strip()
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    )
    return words or ("plana", "普拉娜", "普拉纳")


def _contains_wake_word(text: str, wake_words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in wake_words)


def _is_direct_name_wake(text: str, wake_words: tuple[str, ...]) -> bool:
    lowered = " ".join(str(text or "").strip().lower().split())
    if not lowered or not _contains_wake_word(lowered, wake_words):
        return False
    if any(token in lowered for token in _MENTION_ONLY_TOKENS):
        return False
    if any(token in lowered for token in _DIRECTED_NAME_WAKE_TOKENS):
        return True
    if any(token in lowered for token in _DIRECTED_AFTER_NAME_ACTION_TOKENS):
        return True
    if not _starts_with_wake_word(lowered, wake_words):
        return False
    return any(token in lowered for token in _WAKE_START_ACTION_TOKENS)


def _looks_like_codex_work_request(text: str) -> bool:
    lowered = " ".join(str(text or "").strip().lower().split())
    return any(token in lowered for token in ("workflow", "工作流", "流程")) and any(
        token in lowered
        for token in ("create", "build", "design", "创建", "建立", "设计")
    )


def _starts_with_wake_word(lowered: str, wake_words: tuple[str, ...]) -> bool:
    text = lowered.lstrip()
    for raw_word in wake_words:
        word = raw_word.strip().lower()
        if not word or not text.startswith(word):
            continue
        if len(text) == len(word):
            return True
        next_char = text[len(word)]
        if not (next_char.isascii() and (next_char.isalnum() or next_char == "_")):
            return True
    return False


def _is_poke_event(event: AstrMessageEvent, text: str) -> bool:
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
    lowered = " ".join(piece for piece in pieces if piece).lower()
    return any(
        marker in lowered
        for marker in ("poke", "nudge", "戳一戳", "戳了戳", "拍一拍", "pokenotify")
    )


def _is_private(event: AstrMessageEvent) -> bool:
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


def _is_webchat(event: AstrMessageEvent) -> bool:
    for name in ("get_platform_name", "get_platform_id"):
        getter = getattr(event, name, None)
        if not callable(getter):
            continue
        try:
            if str(getter() or "").strip().lower() == "webchat":
                return True
        except Exception:  # noqa: BLE001
            continue
    platform = getattr(event, "platform_meta", None) or getattr(event, "platform", None)
    for attr in ("name", "id"):
        value = getattr(platform, attr, "")
        if str(value or "").strip().lower() == "webchat":
            return True
    return str(getattr(event, "unified_msg_origin", "") or "").startswith("webchat:")


def _message_text(event: AstrMessageEvent) -> str:
    try:
        return str(event.get_message_str() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _is_command_like(text: str) -> bool:
    lowered = " ".join(str(text or "").strip().lower().split())
    if not lowered:
        return False
    if lowered.startswith("/"):
        return True
    command_prefixes = (
        "plana status",
        "plana mode",
        "plana search",
        "plana remember",
        "plana help",
        "lmem status",
        "lmem search",
        "lmem forget",
        "lmem rebuild-index",
        "lmem rebuild-graph",
        "lmem webui",
        "lmem summarize",
        "lmem reset",
        "lmem cleanup",
        "lmem help",
    )
    return any(
        lowered == prefix or lowered.startswith(prefix + " ")
        for prefix in command_prefixes
    )
