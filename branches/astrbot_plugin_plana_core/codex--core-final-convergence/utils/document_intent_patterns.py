from __future__ import annotations

import re


_DOCUMENT_REFERENCE_TOKENS = (
    "文档",
    "指南",
    "说明书",
    "接口说明",
    "接口文档",
    "api 文档",
    "api文档",
    "reference",
    "documentation",
    "docs",
    "guide",
    "manual",
)

_INFORMATIONAL_TOKENS = (
    "说明",
    "介绍",
    "解释",
    "概述",
    "总结",
    "核心要求",
    "列出文档名",
    "列出文件名",
    "是什么",
    "有什么",
    "如何设计",
    "怎么设计",
    "如何注册",
    "怎么注册",
    "如何配置",
    "怎么配置",
    "how to",
    "explain",
    "describe",
    "summarize",
    "what is",
    "requirements",
)

_DOCUMENT_SIDE_EFFECT_RE = re.compile(
    r"(?:"
    r"(?:按照|根据|照着|依照).{0,24}(?:文档|指南|说明书).{0,16}"
    r"(?:执行|运行|安装|创建|删除|修改|覆盖|移动|重启|部署|写入|下载)"
    r"|(?:执行|运行).{0,12}(?:文档|指南|说明书).{0,12}(?:命令|脚本|步骤|操作)?"
    r"|(?:帮我|替我|直接|现在|立即|马上).{0,12}"
    r"(?:执行|运行|安装|创建|删除|修改|覆盖|移动|重启|部署|写入|下载)"
    r")",
    re.I,
)


def looks_like_document_side_effect_request(text: str) -> bool:
    return bool(_DOCUMENT_SIDE_EFFECT_RE.search(str(text or "").lower()))


def looks_like_informational_document_request(text: str) -> bool:
    """Return whether a turn asks about documentation rather than executing it."""
    lowered = " ".join(str(text or "").lower().split())
    if not any(token in lowered for token in _DOCUMENT_REFERENCE_TOKENS):
        return False
    if looks_like_document_side_effect_request(lowered):
        return False
    return any(token in lowered for token in _INFORMATIONAL_TOKENS)
