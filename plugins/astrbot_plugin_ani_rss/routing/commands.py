from __future__ import annotations

import re
from typing import Any

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent
from astrbot.core.star.filter.custom_filter import CustomFilter

from ..workflows import workflow_from_pending_shortcut

ANIRSS_COMMAND_NAMES = ("anirss", "ani-rss", "ani", "追番", "番剧订阅")
PENDING_SHORTCUT_TEXT_KEY = "ani_rss_pending_shortcut_text"


def normalize_task_ref(value: str) -> str:
    text = str(value or "").strip().lower()
    if re.search(r"\bani-[0-9a-f]{3,8}\b", text):
        return ""
    prefixed = re.search(
        r"(?<![0-9a-z_\u4e00-\u9fff])ani([0-9a-f]{3,8})(?![0-9a-z_\u4e00-\u9fff])",
        text,
    )
    if prefixed:
        return f"ani{prefixed.group(1)}"
    return ""


def normalize_wake_prefixes(value: Any) -> list[str]:
    if isinstance(value, str):
        prefixes = [value]
    elif isinstance(value, list | tuple | set):
        prefixes = [str(item) for item in value]
    else:
        prefixes = []
    cleaned = [prefix.strip() for prefix in prefixes if str(prefix).strip()]
    return cleaned or ["/"]


def configured_wake_prefixes(cfg: Any) -> list[str]:
    prefixes: list[str] = []
    if not hasattr(cfg, "get"):
        return prefixes

    prefixes.extend(_prefix_items(cfg.get("wake_prefix", [])))
    provider_settings = cfg.get("provider_settings", {})
    if hasattr(provider_settings, "get"):
        prefixes.extend(_prefix_items(provider_settings.get("wake_prefix", "")))

    seen: set[str] = set()
    cleaned: list[str] = []
    for prefix in prefixes:
        if prefix and prefix not in seen:
            cleaned.append(prefix)
            seen.add(prefix)
    return cleaned


def pending_shortcut_text(event: AstrMessageEvent, cfg: AstrBotConfig) -> str:
    text = event.get_message_str()
    if event.is_at_or_wake_command:
        return text
    return strip_configured_prefix(text, cfg)


def strip_configured_prefix(text: str, cfg: Any) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    for prefix in sorted(configured_wake_prefixes(cfg), key=len, reverse=True):
        stripped = strip_prefix(raw, prefix)
        if stripped != raw:
            return stripped
    return ""


def strip_prefix(text: str, prefix: str) -> str:
    raw = str(text or "").strip()
    clean_prefix = str(prefix or "").strip()
    if not clean_prefix or not raw.startswith(clean_prefix):
        return raw
    rest = raw[len(clean_prefix) :]
    if re.search(r"[\w\u4e00-\u9fff]$", clean_prefix):
        if rest and not rest[0].isspace():
            return raw
    return rest.strip()


def format_command(prefix: str, command: str) -> str:
    prefix = str(prefix or "").strip()
    command = str(command or "").strip()
    if not prefix:
        return command
    if re.search(r"[\w\u4e00-\u9fff]$", prefix):
        return f"{prefix} {command}"
    return f"{prefix}{command}"


def split_command_tail(text: str, command_names: tuple[str, ...]) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    for command in sorted(command_names, key=len, reverse=True):
        if normalized == command:
            return "help", ""
        if normalized.startswith(f"{command} "):
            tail = normalized[len(command) :].strip()
            workflow, _, args = tail.partition(" ")
            return workflow or "help", args.strip()
    return "", ""


def is_invalid_pending_shortcut(text: str) -> bool:
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    return any(
        re.fullmatch(pattern, raw, flags=re.IGNORECASE)
        for pattern in (
            r"ani-[0-9a-f]{3,8}(?:\s+.+)?",
            r"(?=[0-9a-f]*[a-f])[0-9a-f]{3,8}(?:\s+.+)?",
            r"(?:继续|恢复|接着|continue|cont|continuc)\s*ani-?[0-9a-f]{3,8}(?:\s+.+)?",
        )
    )


class PendingShortcutFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        text = pending_shortcut_text(event, cfg)
        if not text:
            return False
        if workflow_from_pending_shortcut(text) is None:
            return False
        event.set_extra(PENDING_SHORTCUT_TEXT_KEY, text)
        return True


class InvalidPendingShortcutFilter(CustomFilter):
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        text = pending_shortcut_text(event, cfg)
        if not text:
            return False
        if not is_invalid_pending_shortcut(text):
            return False
        event.set_extra(PENDING_SHORTCUT_TEXT_KEY, text)
        return True


def _prefix_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
