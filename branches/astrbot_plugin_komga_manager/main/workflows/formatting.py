from __future__ import annotations

import json
from typing import Any


def format_tool_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def format_user_payload(payload: dict[str, Any]) -> str:
    if payload.get("action") == "write_pending":
        operation = str(payload.get("operation") or "")
        arguments = payload.get("arguments") or {}
        target = next(iter(arguments.values()), "未指定目标") if isinstance(arguments, dict) else "未指定目标"
        return f"待确认 Komga 操作：{operation}\n目标：{target}\n插件未执行任何写入。"
    if not payload.get("ok"):
        return f"Komga 请求失败：{payload.get('error') or 'unknown error'}"
    operation = str(payload.get("operation") or "")
    result = payload.get("result")
    if isinstance(result, list):
        if not result:
            return f"Komga {operation} 查询成功，没有匹配结果。"
        lines = [f"Komga {operation}：{len(result)} 项"]
        for index, item in enumerate(result[:30], start=1):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("title") or item.get("id") or "(unnamed)"
            item_id = item.get("id") or ""
            lines.append(f"{index}. {name}" + (f" [{item_id}]" if item_id else ""))
        return "\n".join(lines)
    return json.dumps(result, ensure_ascii=False, indent=2)

