from __future__ import annotations

import re


SERVICE_TARGETS = (
    "下载器",
    "qbittorrent",
    "qb",
    "机器人",
    "qq",
    "实例",
    "ncqq",
    "ani-rss",
    "ani rss",
    "mikan",
    "订阅",
    "komga",
    "漫画库",
)

SERVICE_INSPECTION_MARKERS = (
    "帮我看看",
    "帮我看下",
    "帮我查",
    "查一下",
    "查下",
    "检查一下",
    "检查下",
    "看一下当前",
    "查看当前",
    "当前状态",
    "现在状态",
    "怎么了",
    "咋了",
    "列出",
    "只查询",
    "只读",
    "获取二维码",
    "登录二维码",
    "码发我",
)

SERVICE_DISCUSSION_MARKERS = (
    "是什么意思",
    "代表什么意思",
    "什么含义",
    "什么原因",
    "为什么",
    "为啥",
    "怎么解决",
    "怎么排查",
    "咋排查",
    "如何排查",
    "怎么办",
    "有没有解决办法",
    "有啥办法",
    "一般咋",
    "一般怎么",
    "怎么配置",
    "怎么添加",
    "如何配置",
    "如何添加",
    "有没有人遇到",
    "除了",
    "替代",
)

NCQQ_INSTANCE_PATTERN = re.compile(r"(?<![a-z0-9_-])(?:accept-)?ncqq-[a-z0-9][a-z0-9_-]{2,79}")
NCQQ_INSTANCE_INSPECTION_MARKERS = (
    "看看",
    "看下",
    "查一下",
    "查下",
    "怎么没登录",
    "为什么没登录",
    "起来没",
    "起来了吗",
    "运行没",
    "启动没",
    "在线吗",
    "掉了吗",
)


def looks_like_service_discussion_request(text: str) -> bool:
    """Return whether service words are used for discussion rather than inspection."""
    lowered = " ".join(str(text or "").lower().split())
    explicit_ncqq_inspection = bool(NCQQ_INSTANCE_PATTERN.search(lowered)) and any(
        token in lowered for token in NCQQ_INSTANCE_INSPECTION_MARKERS
    )
    return (
        any(token in lowered for token in SERVICE_TARGETS)
        and any(token in lowered for token in SERVICE_DISCUSSION_MARKERS)
        and not explicit_ncqq_inspection
    )


def looks_like_service_inspection_request(text: str) -> bool:
    """Return whether the user explicitly asks to inspect a local service."""
    lowered = " ".join(str(text or "").lower().split())
    if any(token in lowered for token in SERVICE_TARGETS) and any(
        token in lowered for token in SERVICE_INSPECTION_MARKERS
    ):
        return True
    return bool(NCQQ_INSTANCE_PATTERN.search(lowered)) and any(
        token in lowered for token in NCQQ_INSTANCE_INSPECTION_MARKERS
    )


def service_domain_profile(text: str) -> str:
    """Classify only the owning business-plugin domain, never a capability."""
    lowered = " ".join(str(text or "").casefold().split())
    ani_colloquial = bool(
        re.search(
            r"(?:追了|在追|正在追|追的|想追|给我追|帮我追).{0,12}(?:哪些|什么|啥|番|动画|新番)|"
            r"(?:哪些|什么|啥).{0,12}(?:番|动画|新番).{0,8}(?:在追|订了)|"
            r"(?:帮我|给我|麻烦)?\s*追一下\s*[^，。！？!?]{2,40}",
            lowered,
        )
    )
    standalone_ani = bool(re.search(r"(?<![a-z0-9])ani(?![a-z0-9])", lowered))
    if ani_colloquial or standalone_ani or any(
        token in lowered
        for token in (
            "mikan",
            "蜜柑",
            "ani-rss",
            "ani rss",
            "订阅",
            "订了",
            "追番",
            "番剧",
            "字幕组",
        )
    ):
        return "ani_plugin"
    if any(token in lowered for token in ("ncqq", "napcat", "机器人", "实例", "登录码", "二维码")) or re.search(
        r"(?<![a-z0-9])(?:那个|这个|我的|咱们的)?\s*qq(?![a-z0-9])",
        lowered,
    ):
        return "ncqq_plugin"
    if any(token in lowered for token in ("komga", "漫画库", "书库")):
        return "komga_plugin"
    return ""
