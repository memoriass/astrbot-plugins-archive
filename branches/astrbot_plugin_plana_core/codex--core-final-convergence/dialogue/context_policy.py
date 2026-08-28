from __future__ import annotations

from typing import Any

from .tool_policy import SEARCH_TOOL_CANDIDATES, intent_chat_tool_names


CONTROLLED_TOOL_ROUTE_PREFIX = "[Plana controlled tool route]"


class DialogueContextPolicy:
    """Build prompt context for companion dialogue and one selected domain."""

    async def build_prompt_block(
        self,
        runtime: Any,
        event: Any,
        provider: Any,
        *,
        behavior: Any | None = None,
        tool_profile: str = "",
    ) -> str:
        query = event.get_message_str().strip()
        selected_profile = tool_profile or ""
        if selected_profile == "ani_plugin":
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- This turn belongs to the ANI-RSS plugin. Call only `ani_rss`.\n"
                "- Use workflow `ai_dispatch` and pass the user's complete natural wording as `target`; do not translate it into a Core capability.\n"
                "- The ANI-RSS plugin owns intent selection, parameter extraction, clarification, pending tasks, and write confirmation.\n"
                "- Do not call search, shell, workspace, or remote execution.\n"
                "- Answer only from the plugin result and do not expose workflow ids or internal capability names."
            )
        if selected_profile == "ncqq_plugin":
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- This turn belongs to the NCQQ Manager plugin. Call only `ncqq_manager`.\n"
                "- Use workflow `ai_dispatch` and pass the user's complete natural wording as `target`; do not choose an internal health capability.\n"
                "- The NCQQ plugin owns target resolution, permissions, approval, clarification, and execution.\n"
                "- Do not call search, shell, workspace, or remote execution.\n"
                "- Answer only from the plugin result and do not expose workflow ids or internal capability names."
            )
        if selected_profile == "komga_plugin":
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- This turn belongs to the Komga Manager plugin. Call only `komga_manager`.\n"
                "- Use workflow `ai_dispatch` and pass the user's complete natural wording as `target`; the plugin selects one bounded read operation or governed write proposal.\n"
                "- Do not choose capability names or bypass confirmation.\n"
                "- Answer only from the plugin result."
            )
        if selected_profile == "service_query":
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- No generic service tool is exposed in this turn.\n"
                "- Ask the user to identify the NCQQ, ANI-RSS, or Komga domain so Core can mount exactly one domain entry.\n"
                "- Do not infer current external state from memory or claim that a live check happened."
            )
        if _looks_like_memory_query(query):
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- This turn is a read-only memory recall request.\n"
                "- Call `plana_recall_memory` with the user's actual subject, then summarize only supported evidence.\n"
                "- Do not create a workflow, request confirmation, hand off to Codex, or expose internal memory IDs.\n"
                "- If evidence is insufficient, say what is missing instead of inventing a remembered fact."
            )
        intent_tools = intent_chat_tool_names(query)
        search_tools = sorted(intent_tools.intersection(SEARCH_TOOL_CANDIDATES))
        if selected_profile == "search" and not search_tools:
            search_tools = ["web_search_searxng"]
        if search_tools:
            joined = ", ".join(f"`{name}`" for name in search_tools[:4])
            return (
                f"{CONTROLLED_TOOL_ROUTE_PREFIX}\n"
                "- This turn explicitly asks for external search.\n"
                f"- Use only the registered search tool {joined}. Do not invent or call any other tool name.\n"
                "- Base the answer only on the returned live result items and include their sources.\n"
                "- Treat Mikan availability as unverified unless a returned URL is from Mikan.\n"
                "- If the tool reports unavailable, empty, or invalid_response, state that result directly.\n"
                "- Do not use memory recall, shell, workspace, skills, or remote execution for this request."
            )
        action = str(getattr(behavior, "action", "") or "")
        chat_profile = action in {"direct_answer", "silence"}
        query_plan = await runtime.plan_memory_query(query, provider)
        memory_query = query_plan.query if query_plan.should_retrieve else query
        selected = None
        if not chat_profile:
            selected = await runtime.select_concept_nodes_for_prompt(memory_query, provider)
        base = runtime.build_prompt_for_event(
            event,
            memory_query,
            concept_nodes=selected,
            profile="chat" if chat_profile else "task",
        )
        unified_recall = getattr(runtime, "unified_recall", None)
        if unified_recall is not None:
            identity = runtime.identity_from_event(event)
            knowledge_block = await unified_recall.prompt_block(
                memory_query,
                scope_id=runtime.resolve_scope(event.unified_msg_origin),
                actor_id=str(getattr(identity, "global_user_id", "") or ""),
                unified_msg_origin=str(event.unified_msg_origin or ""),
                profile="chat" if chat_profile else "task",
            )
            if knowledge_block:
                base = f"{base}\n{knowledge_block}".strip()
        if not chat_profile and bool(runtime.config.get("assistant_remote_runner_enabled", False)):
            handoff_block = (
                "[Plana external execution policy]\n"
                "- Complex browser, code, multi-page investigation, and long-running goals are proposed by Core after this turn.\n"
                "- Do not invent an execution tool, confirmation, lease, skill inspection, or runner result.\n"
                "- Explain the bounded goal and risk plainly; Core owns proposal generation and user authorization."
            )
            base = f"{base}\n{handoff_block}".strip()
        ledger_block = self._ledger_block(runtime, event, query, chat_profile=chat_profile)
        if ledger_block:
            return f"{base}\n{ledger_block}".strip()
        return base

    def _ledger_block(
        self,
        runtime: Any,
        event: Any,
        query: str,
        *,
        chat_profile: bool = False,
    ) -> str:
        ledger = getattr(runtime, "dialogue_ledger", None)
        if ledger is None:
            return ""
        try:
            default_limit = 4 if chat_profile else 8
            limit = int(runtime.config.get("dialogue_ledger_prompt_limit", default_limit))
        except (TypeError, ValueError):
            limit = 8
        if limit <= 0:
            return ""
        if chat_profile:
            limit = min(limit, 4)
        return ledger.prompt_block(
            str(getattr(event, "unified_msg_origin", "") or "global"),
            limit=min(limit, 20),
            exclude_latest_text=query,
        )


def _looks_like_memory_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        token in lowered
        for token in (
            "search memory",
            "memory search",
            "recall",
            "use memory",
            "from memory",
            "查记忆",
            "搜索记忆",
            "检索记忆",
            "调用记忆",
            "使用记忆",
            "从记忆",
            "根据记忆",
            "回忆一下",
            "回忆下",
            "我之前说过",
            "之前提到",
            "还记得",
            "记忆里",
        )
    )
