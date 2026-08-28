from __future__ import annotations

from typing import Any

from .domain_contracts import DOMAIN_PLUGINS


DOMAIN_TOOL_PROFILES = {"ani_plugin", "ncqq_plugin", "komga_plugin"}

_FOLLOWUP_PREFIXES = (
    "那刚才那个",
    "刚才那个",
    "那这个",
    "那它",
    "那就",
    "继续",
    "接着",
)

_FOLLOWUP_OPERATION_TOKENS = (
    "起来",
    "状态",
    "查一下",
    "查下",
    "再查",
    "看看",
    "登录",
    "二维码",
    "登录码",
    "重启",
    "启动",
    "停止",
    "删除",
    "删",
    "处理",
    "弄好",
    "再试",
    "码发我",
    "数据",
    "清掉",
)

_APPROVAL_PREFIXES = (
    "确认",
    "确定",
    "批准",
    "同意",
    "就按这个",
    "就这么办",
    "取消",
    "算了",
    "不弄了",
    "别弄",
    "不用了",
)

_DISCUSSION_TOKENS = ("技术", "方案", "文档", "原理", "是不是", "是否合理")


def is_domain_followup_text(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().casefold().split())
    if not normalized:
        return False
    if normalized.startswith(_APPROVAL_PREFIXES):
        return not any(token in normalized for token in _DISCUSSION_TOKENS) or any(
            token in normalized for token in _FOLLOWUP_OPERATION_TOKENS
        )
    return normalized.startswith(_FOLLOWUP_PREFIXES) and any(
        token in normalized for token in _FOLLOWUP_OPERATION_TOKENS
    )


def normalize_domain_tool_arguments(
    profile: str,
    tool_name: str,
    text: str,
    tool_args: Any,
) -> bool:
    """Force domain-plugin calls to receive the original user wording."""
    descriptor = DOMAIN_PLUGINS.for_profile(profile)
    if descriptor is None or descriptor.tool_name != tool_name:
        return False
    if not isinstance(tool_args, dict):
        return False
    tool_args.clear()
    tool_args.update(descriptor.dispatch_arguments(text))
    return True
