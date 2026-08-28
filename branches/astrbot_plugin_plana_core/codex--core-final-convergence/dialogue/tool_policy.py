from __future__ import annotations

import re
from typing import Any

try:
    from astrbot.api import logger
except Exception:  # noqa: BLE001
    import logging

    logger = logging.getLogger(__name__)

try:
    from ..utils.intent_patterns import native_tool_profile
except ImportError:  # pragma: no cover - top-level script import fallback
    from utils.intent_patterns import native_tool_profile


DEFAULT_CHAT_TOOL_ALLOWLIST = ("plana_recall_memory",)
SEARCH_TOOL_CANDIDATES = (
    "web_search_searxng",
    "web_search_tavily",
    "web_search_bocha",
    "web_search_brave",
    "web_search_firecrawl",
    "web_search_baidu",
    "tavily_extract_web_page",
    "firecrawl_extract_web_page",
    "web_search",
    "search",
)
_OVERFLOW_TOOL = "astrbot_file_read_tool"
_PROFILE_TOOLS: dict[str, tuple[str, ...]] = {
    "memory": ("plana_recall_memory",),
    "search": ("web_search_searxng",),
    "workspace_read": (_OVERFLOW_TOOL, "astrbot_grep_tool"),
    "network": ("astrbot_network_probe", _OVERFLOW_TOOL),
    "download": ("astrbot_download_url", _OVERFLOW_TOOL),
    "service_query": (),
    "ani_plugin": ("ani_rss",),
    "ncqq_plugin": ("ncqq_manager",),
    "komga_plugin": ("komga_manager",),
}

_SERVICE_DOMAIN_PROFILES = {
    "ani_rss": "ani_plugin",
    "ncqq": "ncqq_plugin",
    "komga": "komga_plugin",
}


def restrict_default_chat_tools(
    request_obj: Any,
    config: dict[str, Any],
    text: str = "",
    *,
    profile: str = "",
    astr_context: Any | None = None,
) -> None:
    """Replace the request tools with a public request-scoped ToolSet view."""
    selected_profile = profile or native_tool_profile(text)
    allowed = (
        set(_PROFILE_TOOLS.get(selected_profile, ()))
        if (
            bool(config.get("assistant_native_tool_mode", True))
            and bool(config.get("assistant_low_risk_autorun", True))
            and selected_profile
        )
        else default_chat_tool_allowlist(config, text)
    )
    current = getattr(request_obj, "func_tool", None)
    available = {
        str(getattr(tool, "name", "") or ""): tool
        for tool in list(getattr(current, "tools", []) or [])
        if str(getattr(tool, "name", "") or "")
    }
    missing = allowed.difference(available)
    if missing and astr_context is not None:
        try:
            manager = astr_context.get_llm_tool_manager()
        except Exception:  # noqa: BLE001
            manager = None
        get_func = getattr(manager, "get_func", None)
        if callable(get_func):
            for name in missing:
                try:
                    tool = get_func(name)
                except Exception:  # noqa: BLE001
                    logger.debug("Plana public tool lookup failed: %s", name, exc_info=True)
                    continue
                if tool is not None and bool(getattr(tool, "active", True)):
                    available[name] = tool
    selected = []
    for name in allowed:
        tool = available.get(name)
        if tool is None or not bool(getattr(tool, "active", True)):
            continue
        selected.append(tool)
    try:
        from astrbot.core.agent.tool import ToolSet

        request_obj.func_tool = ToolSet(selected)
    except Exception:  # noqa: BLE001
        if current is None:
            logger.debug("Plana request-scoped ToolSet unavailable outside AstrBot")
            return
        try:
            fallback = type(current)(selected)
            expected_names = [str(getattr(tool, "name", "")) for tool in selected]
            actual_names = [
                str(getattr(tool, "name", ""))
                for tool in list(getattr(fallback, "tools", []) or [])
            ]
            if actual_names != expected_names:
                fallback = type(current)([])
                add_tool = getattr(fallback, "add_tool", None)
                if callable(add_tool):
                    for tool in selected:
                        add_tool(tool)
                elif hasattr(fallback, "tools"):
                    fallback.tools = list(selected)
                else:
                    raise TypeError("request_toolset_population_unavailable")
            request_obj.func_tool = fallback
        except Exception:  # noqa: BLE001
            logger.error("Plana request-scoped ToolSet fallback unavailable; disabling tools")
            if current is not None and hasattr(current, "tools"):
                current.tools = []
                request_obj.func_tool = current
            else:
                request_obj.func_tool = None
            _scrub_context_tool_history(request_obj, set())
            return
    _scrub_context_tool_history(request_obj, {str(getattr(tool, "name", "")) for tool in selected})
    logger.debug(
        "Plana request tool profile=%s allowed=%s selected=%s",
        selected_profile or "chat",
        sorted(allowed),
        [str(getattr(tool, "name", "")) for tool in selected],
    )


def attach_intent_tools(request_obj: Any, text: str, astr_context: Any | None) -> None:
    """Compatibility hook; request-scoped attachment occurs in the policy pass."""
    _ = request_obj, text, astr_context


def default_chat_tool_allowlist(config: dict[str, Any], text: str = "") -> set[str]:
    profile = native_tool_profile(text)
    if profile:
        return set(_PROFILE_TOOLS.get(profile, ()))
    raw = config.get(
        "dialogue_allowed_chat_tools",
        ",".join(DEFAULT_CHAT_TOOL_ALLOWLIST),
    )
    if isinstance(raw, str):
        values = re.split(r"[,;\s]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = DEFAULT_CHAT_TOOL_ALLOWLIST
    allowed = {str(value).strip() for value in values if str(value).strip()}
    return allowed


def intent_chat_tool_names(text: str) -> set[str]:
    return set(_PROFILE_TOOLS.get(native_tool_profile(text), ()))


def tool_profile_for_text(text: str) -> str:
    return native_tool_profile(text)


def service_tool_profile(service_ref: str, capability: str) -> str:
    """Return the single business-plugin profile for a registered capability."""
    capability_domain = str(capability or "").partition(".")[0].casefold()
    if capability_domain in _SERVICE_DOMAIN_PROFILES:
        return _SERVICE_DOMAIN_PROFILES[capability_domain]
    service_domain = str(service_ref or "").partition(".")[0].casefold()
    return _SERVICE_DOMAIN_PROFILES.get(service_domain, "")


def _scrub_context_tool_history(request_obj: Any, allowed: set[str]) -> None:
    contexts = getattr(request_obj, "contexts", None)
    if not isinstance(contexts, list) or not contexts:
        return
    result_call_ids = {
        str(item.get("tool_call_id") or "")
        for item in contexts
        if isinstance(item, dict)
        and str(item.get("role") or "") in {"tool", "function"}
        and str(item.get("tool_call_id") or "")
    }
    cleaned: list[dict[str, Any]] = []
    allowed_call_ids: set[str] = set()
    for item in contexts:
        if not isinstance(item, dict):
            cleaned.append(item)
            continue
        role = str(item.get("role") or "")
        if role in {"tool", "function"}:
            name = str(item.get("name") or "")
            call_id = str(item.get("tool_call_id") or "")
            if not call_id or call_id not in allowed_call_ids:
                continue
            if name and name not in allowed:
                continue
            cleaned.append(item)
            continue
        if role == "assistant" and isinstance(item.get("tool_calls"), list):
            copied = dict(item)
            copied["content"] = _history_text_content(copied.get("content"))
            had_allowed_call = any(
                _tool_call_name(call) in allowed for call in item["tool_calls"]
            )
            filtered_calls = [
                call
                for call in item["tool_calls"]
                if _tool_call_name(call) in allowed
                and isinstance(call, dict)
                and str(call.get("id") or "") in result_call_ids
            ]
            if filtered_calls:
                copied["tool_calls"] = filtered_calls
                allowed_call_ids.update(
                    str(call.get("id") or "")
                    for call in filtered_calls
                    if isinstance(call, dict) and str(call.get("id") or "")
                )
                cleaned.append(copied)
            elif had_allowed_call and str(copied.get("content") or "").strip():
                copied.pop("tool_calls", None)
                cleaned.append(copied)
            continue
        if role == "assistant":
            copied = dict(item)
            copied["content"] = _history_text_content(copied.get("content"))
            copied.pop("tool_calls", None)
            if not str(copied.get("content") or "").strip():
                continue
            cleaned.append(copied)
            continue
        cleaned.append(item)
    request_obj.contexts = cleaned


def _tool_call_name(call: Any) -> str:
    if not isinstance(call, dict):
        return ""
    function = call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return str(call.get("name") or "")


def _history_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = str(part.get("type") or "")
        if part_type not in {"text", "input_text", "output_text"}:
            continue
        value = part.get("text")
        if isinstance(value, dict):
            value = value.get("value")
        if str(value or "").strip():
            texts.append(str(value))
    return "\n".join(texts)
