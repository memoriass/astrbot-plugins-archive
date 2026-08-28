from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NATURAL_LANGUAGE_INTENT_RE = (
    r"(?i)(?:"
    r"(?:列出|推荐|看看|看下|来点|有什么|有没有).{0,50}(?:当季|本季|当前季度|新番|番剧|动画|追番|推荐)"
    r"|(?:帮我|给我|请|麻烦)\s*(?:把|将)?\s*(?:添加|下载|订阅|追番|加入).{1,80}"
    r"|(?:添加|下载|订阅|追番|加入).{1,80}(?:到|进|至|加入)\s*(?:ani|ani-rss|anirss|nas|rss|订阅)"
    r"|(?:把|将).{1,80}(?:添加|下载|订阅|追番|加入)(?:到|进|至|加入)?\s*(?:ani|ani-rss|anirss|nas|rss|订阅)?"
    r"|(?:搜索|查找|查一下|找一下|搜一下).{0,80}(?:mikan|蜜柑|字幕组|番剧|动画|rss|有没有字幕组)"
    r"|(?:查看|列出|看看|显示|预览).{0,50}(?:ani-rss|anirss|订阅列表|订阅|追番|已启用|运行|正在订阅)"
    r"|(?:刷新|更新).{0,50}(?:ani-rss|anirss|全部订阅|所有订阅|订阅)"
    r"|(?:检查|测试).{0,50}(?:ani-rss|anirss|连接|状态)"
    r")"
)


@dataclass(slots=True)
class WorkflowRequest:
    workflow: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "tool"
    rendered_cards: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    workflow: str
    title: str
    purpose: str
    user_visible: bool = True


COMPILED_WORKFLOWS: dict[str, CompiledWorkflow] = {
    "ai_dispatch": CompiledWorkflow(
        workflow="ai_dispatch",
        title="AI 前置分流",
        purpose="把自然语言或不完整工具参数先分析为受控分支，再转入具体 ANI-RSS workflow。",
    ),
    "add_subscription": CompiledWorkflow(
        workflow="add_subscription",
        title="RSS 直连添加",
        purpose="从已知 RSS URL 构造订阅，用户确认后写入 ANI-RSS。",
    ),
    "add_mikan_subscription": CompiledWorkflow(
        workflow="add_mikan_subscription",
        title="Mikan 搜索添加",
        purpose="按番名搜索 Mikan，交互选择番剧和字幕组，选定字幕组后自动添加。",
    ),
    "recommend_mikan_subscription": CompiledWorkflow(
        workflow="recommend_mikan_subscription",
        title="Mikan 推荐订阅",
        purpose="按季度或关键词拉取 Mikan 列表，结合 ANI-RSS/Bangumi 评分筛选，选定番剧和字幕组后自动添加。",
    ),
    "search_mikan": CompiledWorkflow(
        workflow="search_mikan",
        title="Mikan 搜索",
        purpose="搜索 Mikan 番剧或查看某个 Mikan 番剧页的字幕组 RSS。",
    ),
    "preview_subscription": CompiledWorkflow(
        workflow="preview_subscription",
        title="订阅预览",
        purpose="从 RSS URL 构造订阅并返回 ANI-RSS 预览，不写入订阅；仅用于诊断。",
        user_visible=False,
    ),
    "list_subscriptions": CompiledWorkflow(
        workflow="list_subscriptions",
        title="已启用订阅",
        purpose="列出当前 ANI-RSS 已启用订阅，用于预览正在追番的订阅。",
    ),
    "refresh_subscription": CompiledWorkflow(
        workflow="refresh_subscription",
        title="刷新单个订阅",
        purpose="按订阅 ID 触发 ANI-RSS 刷新。",
    ),
    "refresh_all": CompiledWorkflow(
        workflow="refresh_all",
        title="刷新全部订阅",
        purpose="触发 ANI-RSS 刷新所有订阅。",
    ),
    "check_status": CompiledWorkflow(
        workflow="check_status",
        title="连接检查",
        purpose="诊断 AstrBot 到 ANI-RSS 的 API 连通性；普通业务流程会静默预检。",
        user_visible=False,
    ),
    "continue_pending": CompiledWorkflow(
        workflow="continue_pending",
        title="继续挂起任务",
        purpose="按任务 ID 继续之前挂起的候选选择或确认流程。",
    ),
}

WORKFLOW_ALIASES = {
    "ai": "ai_dispatch",
    "ai_dispatch": "ai_dispatch",
    "dispatch": "ai_dispatch",
    "natural": "ai_dispatch",
    "assistant": "ai_dispatch",
    "workflow": "ai_dispatch",
    "助手": "ai_dispatch",
    "分流": "ai_dispatch",
    "路由": "ai_dispatch",
    "自然语言": "ai_dispatch",
    "add": "add_subscription",
    "add_rss": "add_subscription",
    "add_mikan": "add_mikan_subscription",
    "mikan_add": "add_mikan_subscription",
    "订阅": "add_mikan_subscription",
    "添加": "add_mikan_subscription",
    "添加订阅": "add_mikan_subscription",
    "新增订阅": "add_mikan_subscription",
    "追番": "add_mikan_subscription",
    "下载": "add_mikan_subscription",
    "recommend": "recommend_mikan_subscription",
    "recommend_mikan": "recommend_mikan_subscription",
    "推荐": "recommend_mikan_subscription",
    "推荐番剧": "recommend_mikan_subscription",
    "推荐新番": "recommend_mikan_subscription",
    "discover": "recommend_mikan_subscription",
    "discover_mikan": "recommend_mikan_subscription",
    "season": "recommend_mikan_subscription",
    "season_mikan": "recommend_mikan_subscription",
    "mikan": "search_mikan",
    "search": "search_mikan",
    "search_mikan_subscription": "search_mikan",
    "搜索": "search_mikan",
    "搜索番剧": "search_mikan",
    "查找": "search_mikan",
    "查找番剧": "search_mikan",
    "preview": "preview_subscription",
    "list": "list_subscriptions",
    "列表": "list_subscriptions",
    "订阅列表": "list_subscriptions",
    "查看订阅": "list_subscriptions",
    "refresh": "refresh_subscription",
    "status": "check_status",
    "状态": "check_status",
    "诊断": "check_status",
    "ping": "check_status",
    "c": "continue_pending",
    "cont": "continue_pending",
    "continue": "continue_pending",
    "continuc": "continue_pending",
    "resume": "continue_pending",
    "继续": "continue_pending",
    "恢复": "continue_pending",
    "接着": "continue_pending",
    "选": "continue_pending",
    "选择": "continue_pending",
    "确认": "continue_pending",
    "取消": "continue_pending",
}

CONFIRM_REPLIES = {
    "确认",
    "确定",
    "确认添加",
    "添加",
    "可以",
    "可以添加",
    "是",
    "是的",
    "好",
    "yes",
    "y",
    "ok",
    "okay",
    "add",
    "confirm",
}

CANCEL_REPLIES = {
    "取消",
    "放弃",
    "不添加",
    "不要",
    "不用",
    "否",
    "no",
    "n",
    "cancel",
    "stop",
}
