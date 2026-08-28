from __future__ import annotations

from typing import Any


async def livingmemory_compat_text(
    runtime: Any,
    event: Any,
    action: str = "status",
    value: str = "",
    *,
    provider: Any | None = None,
) -> str:
    """Map common LivingMemory commands to Plana-native memory services."""

    command = str(action or "status").strip().lower() or "status"
    payload = str(value or "").strip()
    if command == "status":
        return _status_text(runtime, event)
    if command == "search":
        query, limit = _query_and_limit(payload, default_limit=5)
        if not query:
            return "用法：/lmem search <query> [k]"
        return _search_text(runtime, event, query, limit)
    if command == "forget":
        return _forget_text(runtime, event, payload)
    if command == "rebuild-index":
        backup = runtime.maintenance.backup("before-lmem-rebuild-index")
        rebuilt = runtime.maintenance.rebuild_indexes()
        return (
            "LivingMemory 兼容：索引已由 Plana 重建\n"
            f"backup={backup.get('ok')} path={backup.get('path', '')}\n"
            f"indexes={rebuilt.get('count', 0)}"
        )
    if command == "rebuild-graph":
        return await _rebuild_graph_text(runtime, event, provider)
    if command == "webui":
        return _webui_text(runtime)
    if command == "summarize":
        return runtime.consolidate_text(event)
    if command == "reset":
        return _reset_context_text(runtime, event)
    if command == "cleanup":
        return _cleanup_text(runtime, payload)
    if command == "help":
        return _help_text()
    return _help_text()


def _status_text(runtime: Any, event: Any) -> str:
    identity = runtime.identity_from_event(event)
    scope = runtime.resolve_scope(event.unified_msg_origin)
    stats = runtime.memory_kernel.stats(scope, identity.global_user_id)
    counts = stats.get("counts", {})
    atom_store = getattr(getattr(runtime, "memory_storage", None), "atoms", None)
    atom_counts = atom_store.counts(scope) if atom_store is not None else {}
    maintenance = runtime.maintenance.validate()
    return (
        "LivingMemory 兼容状态（Plana-native）\n"
        f"scope={scope}\n"
        f"episodic={counts.get('episodic', 0)} semantic={counts.get('semantic', 0)} "
        f"tool={counts.get('tool_user', 0)}\n"
        f"atoms={atom_counts.get('total', 0)} active={atom_counts.get('active', 0)} "
        f"expired={atom_counts.get('expired', 0)} forgotten={atom_counts.get('forgotten', 0)}\n"
        f"recall_gaps={stats.get('recall_gaps', {})}\n"
        f"maintenance={maintenance.get('status', 'unknown')}"
    )


def _search_text(runtime: Any, event: Any, query: str, limit: int) -> str:
    result = runtime.memory_kernel.search(event.unified_msg_origin, query, "", limit)
    lines = [f"LivingMemory 兼容搜索（Plana recall）：{query}"]
    if result.get("results"):
        lines.append("fused:")
        for index, item in enumerate(result["results"], start=1):
            content = str(_field(item, "content", ""))
            route = str(_field(item, "route", ""))
            score = _field(item, "score", "")
            lines.append(f"{index}. [{route}] score={score} {content[:160]}")
    if result.get("memories"):
        lines.append("episodic:")
        lines.extend(
            f"{item.id}. [{item.kind}] {item.content[:160]}"
            for item in result["memories"][:limit]
        )
    if len(lines) == 1:
        return "LivingMemory 兼容搜索：无结果"
    return "\n".join(lines)


def _forget_text(runtime: Any, event: Any, payload: str) -> str:
    parts = payload.split()
    memory_id = _first_int(parts)
    if memory_id <= 0:
        return "用法：/lmem forget <memory_id> confirm"
    if not any(part.lower() in {"confirm", "确认"} for part in parts[1:]):
        return (
            f"删除记忆需要确认边界：请发送 /lmem forget {memory_id} confirm\n"
            "这会调用 Plana 的审计删除，并级联清理该记忆的 atom/索引。"
        )
    identity = runtime.identity_from_event(event)
    result = runtime.memory_storage.delete_memory(
        memory_id,
        actor=f"lmem:{identity.global_user_id}",
    )
    if result.get("ok"):
        return f"LivingMemory 兼容删除：已删除 memory_id={memory_id}"
    return f"LivingMemory 兼容删除失败：{result.get('error', 'unknown')}"


async def _rebuild_graph_text(runtime: Any, event: Any, provider: Any | None) -> str:
    scope = runtime.resolve_scope(event.unified_msg_origin)
    if provider is None:
        return (
            "LivingMemory 兼容图谱重建：当前无 LLM provider，已跳过概念重建。\n"
            f"nodes={runtime.concept_graph.storage.count_nodes()} "
            f"edges={runtime.concept_graph.storage.count_edges()}"
        )
    result = await runtime.auto_accumulate_concepts(scope, provider)
    return (
        "LivingMemory 兼容图谱重建：已使用 Plana 概念累计器处理\n"
        f"scope={scope}\n"
        f"processed={result.get('processed', 0)} written={result.get('written', 0)} "
        f"skipped={result.get('skipped', 0)}"
    )


def _webui_text(runtime: Any) -> str:
    return (
        "LivingMemory 兼容 WebUI：Plana 使用 AstrBot 嵌入面板。\n"
        "入口：/api/plug/plana/dashboard"
    )


def _reset_context_text(runtime: Any, event: Any) -> str:
    identity = runtime.identity_from_event(event)
    scope = runtime.resolve_scope(event.unified_msg_origin)
    cache = getattr(runtime.memory_kernel, "_last_prompt_context", {})
    key = f"{scope}|{identity.global_user_id}"
    removed = 1 if cache.pop(key, None) is not None else 0
    return f"LivingMemory 兼容 reset：已清理当前会话 prompt 记忆冷却状态 removed={removed}"


def _cleanup_text(runtime: Any, payload: str) -> str:
    mode = payload.strip().lower() or "preview"
    if mode not in {"preview", "exec"}:
        return "用法：/lmem cleanup [preview|exec]"
    validation = runtime.maintenance.validate()
    if mode == "preview":
        return (
            "LivingMemory 兼容 cleanup preview：Plana 不把记忆注入块持久写入历史。\n"
            f"maintenance={validation.get('status', 'unknown')}"
        )
    result = runtime.maintenance.clean_orphans(actor="lmem")
    return (
        "LivingMemory 兼容 cleanup exec：已执行 Plana 孤儿数据清理。\n"
        f"ok={result.get('ok')} cleaned={result.get('cleaned', 0)}"
    )


def _help_text() -> str:
    return (
        "LivingMemory 兼容命令（由 Plana-native 能力承载）：\n"
        "  /lmem status\n"
        "  /lmem search <query> [k]\n"
        "  /lmem forget <id> confirm\n"
        "  /lmem rebuild-index\n"
        "  /lmem rebuild-graph\n"
        "  /lmem webui\n"
        "  /lmem summarize\n"
        "  /lmem reset\n"
        "  /lmem cleanup [preview|exec]\n"
        "  /lmem help"
    )


def _query_and_limit(text: str, default_limit: int) -> tuple[str, int]:
    parts = text.split()
    if len(parts) >= 2:
        try:
            limit = max(1, min(int(parts[-1]), 50))
            return " ".join(parts[:-1]).strip(), limit
        except ValueError:
            pass
    return text.strip(), default_limit


def _first_int(parts: list[str]) -> int:
    for item in parts:
        try:
            return max(0, int(item))
        except ValueError:
            continue
    return 0


def _field(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)
