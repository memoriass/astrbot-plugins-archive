from __future__ import annotations

from typing import Any


_REQUIRED_FIELDS = ("domain_id", "owner", "profile", "tool_name")


def build_domain_harness_web_payload(runtime: Any) -> dict[str, Any]:
    context = getattr(runtime, "astr_context", None)
    get_all_stars = getattr(context, "get_all_stars", None)
    if not callable(get_all_stars):
        return _payload("unsupported", 0, [], ["AstrBot Context.get_all_stars() 当前不可用"])
    try:
        stars = list(get_all_stars() or ())
    except Exception as exc:  # noqa: BLE001
        return _payload("issue", 0, [], [f"读取 AstrBot 插件注册表失败：{_safe_error(exc)}"])

    active_plugins = 0
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_profiles: set[str] = set()
    seen_tools: set[str] = set()
    for metadata in stars:
        if not bool(getattr(metadata, "activated", False)):
            continue
        active_plugins += 1
        plugin = getattr(metadata, "star_cls", None)
        provider = getattr(plugin, "domain_harness_descriptors", None)
        if not callable(provider):
            continue
        plugin_name = str(getattr(metadata, "name", "") or type(plugin).__name__).strip()
        try:
            descriptors = provider() or ()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{plugin_name}：descriptor provider 调用失败（{_safe_error(exc)}）")
            continue
        for index, value in enumerate(descriptors):
            try:
                item = _descriptor_item(value, plugin_name)
                profile_key = item["profile"].casefold()
                tool_key = item["technical"]["tool_name"].casefold()
                if profile_key in seen_profiles:
                    raise ValueError(f"profile 重复：{item['profile']}")
                if tool_key in seen_tools:
                    raise ValueError("tool_name 重复")
                seen_profiles.add(profile_key)
                seen_tools.add(tool_key)
                items.append(item)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{plugin_name} descriptor #{index + 1}：{_safe_error(exc)}")

    status = "issue" if errors else "available" if items else "empty"
    return _payload(status, active_plugins, items, errors)


def _descriptor_item(value: Any, plugin_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("descriptor 必须是对象")
    schema_version = int(value.get("schema_version") or 0)
    if schema_version != 1:
        raise ValueError(f"不支持 schema_version={schema_version}")
    normalized = {
        "domain_id": str(value.get("domain_id") or value.get("domain") or "").strip(),
        "owner": str(value.get("owner") or "").strip(),
        "profile": str(value.get("profile") or "").strip(),
        "tool_name": str(value.get("tool_name") or "").strip(),
    }
    missing = [field for field in _REQUIRED_FIELDS if not normalized[field]]
    if missing:
        raise ValueError(f"缺少字段：{', '.join(missing)}")
    read_operations = _strings(value.get("read_operations"))
    write_operations = _strings(value.get("write_operations"))
    direct_dispatch = bool(value.get("direct_dispatch", False))
    return {
        "id": normalized["domain_id"],
        "name": normalized["owner"],
        "plugin_name": plugin_name,
        "owner": normalized["owner"],
        "profile": normalized["profile"],
        "service_ref": str(value.get("service_ref") or "").strip(),
        "aliases": _strings(value.get("aliases")),
        "read_operations": read_operations,
        "write_operations": write_operations,
        "direct_dispatch": direct_dispatch,
        "supports_continuation": bool(value.get("supports_continuation", True)),
        "discussion_guard": bool(value.get("discussion_guard", True)),
        "status": "ready" if direct_dispatch else "limited",
        "governance": {
            "host_authority": "core",
            "writes_require_confirmation": bool(write_operations),
            "routing_mode": "direct_dispatch" if direct_dispatch else "single_tool_fallback",
        },
        "technical": {
            "schema_version": schema_version,
            "tool_name": normalized["tool_name"],
            "natural_input_field": str(value.get("natural_input_field") or "target").strip(),
            "dispatch_workflow": str(value.get("dispatch_workflow") or "ai_dispatch").strip(),
        },
    }


def _payload(status: str, active_plugins: int, items: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "summary": {
            "active_plugins": active_plugins,
            "discovered": len(items),
            "direct_dispatch": sum(bool(item.get("direct_dispatch")) for item in items),
            "confirmation_governed": sum(bool((item.get("governance") or {}).get("writes_require_confirmation")) for item in items),
            "errors": len(errors),
        },
        "items": items,
        "errors": errors[:12],
    }


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:180] or type(exc).__name__
