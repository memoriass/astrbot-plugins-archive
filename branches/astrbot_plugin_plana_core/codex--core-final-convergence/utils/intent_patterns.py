from __future__ import annotations

import re

from .document_intent_patterns import (
    looks_like_document_side_effect_request,
    looks_like_informational_document_request,
)
from .service_intent_patterns import (
    SERVICE_TARGETS,
    looks_like_service_discussion_request,
    looks_like_service_inspection_request,
    service_domain_profile,
)

TOOL_EXECUTION_VERBS = (
    "run",
    "execute",
    "call",
    "invoke",
    "queue",
    "delegate",
    "handoff",
    "route",
    "schedule",
    "arrange",
    "test",
    "check",
    "inspect",
    "diagnose",
    "scan",
    "open",
    "read",
    "list",
    "search",
    "retrieve",
    "运行",
    "执行",
    "调用",
    "排队",
    "委派",
    "转交",
    "交给",
    "安排",
    "测试",
    "联调",
    "检查",
    "查看",
    "读取",
    "列出",
    "扫描",
    "诊断",
    "搜索",
    "检索",
    "查一下",
    "查下",
    "打开",
    "抓取",
    "爬取",
    "跑一下",
)

TOOL_EXECUTION_TARGETS = (
    "command",
    "shell",
    "terminal",
    "runner",
    "remote runner",
    "vm",
    "virtual machine",
    "sandbox",
    "network",
    "connectivity",
    "url",
    "website",
    "browser",
    "web page",
    "file",
    "folder",
    "directory",
    "path",
    "local",
    "plugin",
    "tool",
    "diagnostic",
    "mikan",
    "ani",
    "ani-rss",
    "anime",
    "命令",
    "终端",
    "外置",
    "隔离",
    "虚拟机",
    "沙盒",
    "网络",
    "连接",
    "网页",
    "网站",
    "浏览器",
    "文件",
    "目录",
    "路径",
    "本地",
    "插件",
    "工具",
    "诊断",
    "番剧",
    "新番",
    "动漫",
    "动画",
)

REMOTE_RUNNER_VERBS = (
    "queue",
    "delegate",
    "handoff",
    "route",
    "schedule",
    "arrange",
    "test",
    "smoke",
    "排队",
    "委派",
    "转交",
    "交给",
    "安排",
    "测试",
    "联调",
)

REMOTE_RUNNER_TARGETS = (
    "codex",
    "runner",
    "remote runner",
    "vm",
    "virtual machine",
    "external brain",
    "外置",
    "隔离",
    "虚拟机",
    "远程执行",
    "外置大脑",
)

def looks_like_tool_execution_request(text: str) -> bool:
    lowered = str(text or "").lower()
    if looks_like_document_side_effect_request(lowered):
        return True
    if looks_like_informational_document_request(lowered):
        return False
    if native_tool_profile(lowered) or looks_like_long_task_request(lowered):
        return True
    if looks_like_explicit_codex_request(lowered):
        return True
    if looks_like_external_search_request(lowered):
        return True
    return any(token in lowered for token in TOOL_EXECUTION_VERBS) and any(
        token in lowered for token in TOOL_EXECUTION_TARGETS
    )


def looks_like_explicit_codex_request(text: str) -> bool:
    lowered = str(text or "").lower()
    negative_patterns = (
        r"(?:不要|不用|无需|不必|别)\s*(?:再)?(?:交给|转交|委派|交由).{0,16}(?:codex|执行部门|远程执行)",
        r"(?:do not|don't|dont|never)\s+(?:delegate|handoff|route).{0,16}(?:codex|runner)",
    )
    if any(re.search(pattern, lowered) for pattern in negative_patterns):
        return False
    return any(token in lowered for token in REMOTE_RUNNER_TARGETS) and any(
        token in lowered for token in REMOTE_RUNNER_VERBS
    )


def looks_like_external_search_request(text: str) -> bool:
    lowered = str(text or "").lower()
    search_tokens = ("search", "搜索", "检索", "搜一下", "搜下", "查一下", "查下")
    negative_search_patterns = (
        r"(?:不需要|不用|不要|无需)\s*(?:联网|网络)?\s*(?:搜索|检索|查)",
        r"(?:do not|don't|dont|no need to)\s+(?:web\s+)?search",
    )
    if any(re.search(pattern, lowered) for pattern in negative_search_patterns):
        return False
    memory_tokens = ("memory", "记忆", "回忆", "lmem")
    if not any(token in lowered for token in search_tokens):
        return False
    if any(token in lowered for token in memory_tokens):
        return False
    return True


def looks_like_external_recommendation_request(text: str) -> bool:
    """Detect conversational recommendations that need current external facts."""
    lowered = " ".join(str(text or "").lower().split())
    recommendation_tokens = (
        "推荐",
        "值得追",
        "值得看",
        "有啥好",
        "有什么好",
        "哪几部",
        "高分",
        "热门",
        "榜单",
        "top",
        "recommend",
        "worth watching",
    )
    external_targets = (
        "mikan",
        "anilist",
        "番剧",
        "新番",
        "动漫",
        "动画",
        "漫画",
        "电影",
        "电视剧",
        "新闻",
        "餐厅",
        "饭店",
        "酒店",
        "旅游",
        "商品",
        "游戏",
        "anime",
        "manga",
        "movie",
        "news",
        "restaurant",
        "hotel",
    )
    current_tokens = (
        "这季度",
        "本季度",
        "本季",
        "这季",
        "最近",
        "近期",
        "现在",
        "今天",
        "今年",
        "current",
        "latest",
        "recent",
        "this season",
    )
    has_recommendation = any(token in lowered for token in recommendation_tokens)
    has_target = any(token in lowered for token in external_targets)
    has_current_context = any(token in lowered for token in current_tokens)
    return has_target and (has_recommendation or has_current_context)


def native_tool_profile(text: str) -> str:
    """Return the bounded AstrBot tool profile for a low-risk request."""
    lowered = " ".join(str(text or "").lower().split())
    if looks_like_informational_document_request(lowered):
        return ""
    if looks_like_service_discussion_request(lowered):
        return ""
    service_domain = service_domain_profile(lowered)
    service_action_request = any(
        token in lowered
        for token in (
            "新建", "创建", "新弄个", "新弄一个", "弄个", "弄一个", "建个", "建一个", "开一个", "加一个", "重启", "启动", "停止",
            "暂停", "恢复运行", "删除", "删掉", "彻底删除", "删除实例", "销毁实例", "重新登录",
            "恢复登录", "发登录码", "发二维码", "接入后端",
            "create", "restart", "start", "stop", "delete", "relogin",
        )
    )
    if service_domain and service_action_request:
        return service_domain
    domain_natural_request = bool(
        service_domain == "ani_plugin"
        and re.search(
            r"(?:帮我|给我|麻烦)?\s*追一下\s*[^，。！？!?]{2,40}|"
            r"(?:看看|看下|查下|检查).{0,16}(?:ani|追了|在追|正在追)|"
            r"(?:ani|追了|在追|正在追).{0,16}(?:状态|哪些|什么|啥|更新)|"
            r"(?:我)?(?:追的|在追的|订的).{0,8}(?:番|动画|新番).{0,16}(?:最近|更新|更了|更到|哪些|什么|啥)",
            lowered,
        )
    )
    if domain_natural_request:
        return service_domain
    if looks_like_service_inspection_request(lowered):
        return service_domain
    urls = re.findall(r"https?://[^\s<>\]\[()]+", lowered)
    mikan_service_request = "mikan" in lowered and any(
        token in lowered
        for token in (
            "看看", "搜", "查", "找", "检索", "番剧", "季度", "本季", "这季",
            "高分", "推荐", "search", "latest", "season",
        )
    )
    if mikan_service_request:
        return "ani_plugin"
    local_komga_request = (
        any(token in lowered for token in ("漫画库", "书库", "komga"))
        and any(token in lowered for token in ("最近", "更新", "新进", "有什么", "有啥", "搜索", "搜", "查", "找"))
    ) or (
        "漫画" in lowered
        and any(token in lowered for token in ("搜索", "搜", "查找", "查一下", "找一下"))
    )
    if local_komga_request:
        return "komga_plugin"
    local_service_request = any(
        token in lowered
        for token in (
            "订了啥", "订了些啥", "我订了", "都订了", "订阅了什么",
            "订阅列表", "订阅清单",
        )
    )
    if local_service_request:
        return service_domain_profile(lowered)
    if looks_like_external_search_request(lowered):
        return "search"
    if looks_like_external_recommendation_request(lowered):
        return "search"
    qr_request = any(
        token in lowered
        for token in (
            "获取二维码", "登录二维码", "登录码", "拉码", "扫码登录",
            "把码发我", "二维码发我", "码发我",
        )
    )
    if qr_request:
        return "ncqq_plugin"
    subscription_request = any(
        token in lowered
        for token in (
            "订了啥", "订了些啥", "我订了", "都订了", "订阅了什么",
            "订阅列表", "订阅清单",
        )
    )
    if subscription_request:
        return "ani_plugin"
    service_targets = (
        "下载器", "qbittorrent", "qb", "机器人", "实例", "ncqq",
        "ani-rss", "ani rss", "订阅", "komga", "漫画库",
    )
    service_states = (
        "掉了", "掉线", "离线", "在线", "没起来", "没起", "起来没",
        "起来了吗", "启动没", "启动了吗", "趴了",
        "状态", "速度", "没速度", "有没有更新", "更新了吗",
    )
    if any(token in lowered for token in service_targets) and any(
        token in lowered for token in service_states
    ):
        return service_domain_profile(lowered)
    if len(urls) == 1 and any(token in lowered for token in ("download", "下载", "保存链接")):
        return "download"
    if any(token in lowered for token in ("dns", "tcp", "http head", "http_head", "端口", "网络探测", "连通性", "解析域名")):
        return "network"
    read_verbs = ("read", "list", "grep", "search file", "查看", "读取", "列出", "搜索文件", "检索文件")
    workspace_targets = ("workspace", "工作区", "文件", "目录", "folder", "directory", "path")
    if any(token in lowered for token in read_verbs) and any(
        token in lowered for token in workspace_targets
    ):
        sensitive = (".env", ".ssh", "id_rsa", "id_ed25519", "cookie", "credential", "secret", "密钥", "凭据")
        unsafe_path = re.search(r"(?:^|\s)(?:[a-z]:[\\/]|/|~|\.\.[\\/])", lowered)
        if any(token in lowered for token in sensitive) or unsafe_path:
            return ""
        return "workspace_read"
    return ""


def prefers_external_search_over_service(text: str) -> bool:
    """Return whether explicit web-search wording should beat a service alias match."""
    lowered = " ".join(str(text or "").lower().split())
    if "mikan" in lowered:
        return False
    if looks_like_external_recommendation_request(lowered):
        return True
    if not looks_like_external_search_request(lowered):
        return False
    return any(
        token in lowered
        for token in (
            "search",
            "\u641c\u7d22",
            "\u68c0\u7d22",
            "\u641c\u4e00\u4e0b",
            "\u641c\u4e0b",
        )
    )


def looks_like_long_task_request(text: str, *, threshold_seconds: int = 120) -> bool:
    """Detect explicit long, diagnostic, batch, or multi-artifact Codex work."""
    lowered = " ".join(str(text or "").lower().split())
    urls = re.findall(r"https?://[^\s<>\]\[()]+", lowered)
    service_diagnostic = (
        any(token in lowered for token in SERVICE_TARGETS)
        and any(token in lowered for token in ("日志", "log", "报错", "错误记录"))
        and any(
            token in lowered
            for token in (
                "认真查", "仔细查", "深入查", "分析", "诊断", "定位",
                "为什么", "原因", "怎么回事", "总掉线", "反复掉线",
            )
        )
    )
    if service_diagnostic:
        return True
    batch_tokens = (
        "batch",
        "bulk",
        "recursive",
        "multiple sites",
        "all links",
        "批量",
        "递归",
        "多站点",
        "所有链接",
        "这些链接",
    )
    build_tokens = (
        "pip install",
        "npm install",
        "pnpm install",
        "yarn install",
        "install dependency",
        "build project",
        "compile project",
        "安装依赖",
        "构建项目",
        "编译项目",
    )
    browser_tokens = (
        "browser automation",
        "complete browser",
        "浏览器自动化",
        "完整浏览器",
    )
    background_tokens = ("background process", "daemon", "后台进程", "持续运行")
    multi_artifact_tokens = ("multiple files", "many files", "多个文件", "多个产物")
    explicit_long_tokens = (
        "long task",
        "long lane",
        "long queue",
        "long 长任务",
        "长任务",
        "长期任务",
        "长队列",
    )
    artifact_execution_tokens = (
        "artifact 回传",
        "artifact return",
        "保存为 artifact",
        "文件产物回传",
        "图片 artifact",
    )
    if len(urls) > 1 or any(token in lowered for token in batch_tokens):
        return True
    duration_match = re.search(r"(?:预计|大约|约|expected|around)?\s*(\d+)\s*(秒|seconds?|分钟|minutes?)", lowered)
    if duration_match:
        duration = int(duration_match.group(1))
        if duration_match.group(2) in {"分钟", "minute", "minutes"}:
            duration *= 60
        if duration > max(1, threshold_seconds):
            return True
    return any(
        token in lowered
        for token in (
            *build_tokens,
            *browser_tokens,
            *background_tokens,
            *multi_artifact_tokens,
            *explicit_long_tokens,
            *artifact_execution_tokens,
        )
    )
