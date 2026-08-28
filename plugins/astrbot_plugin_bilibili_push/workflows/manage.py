from __future__ import annotations

from ..database.aliases import normalize_alias
from ..core.http import HttpClient
from .cards import account_status_card, operation_confirm_card, subscription_list_card
from .formatting import format_accounts, format_subscriptions, format_workflow_list
from .models import WorkflowRequest
from .resolver_stats import format_resolver_stats
from .results import WorkflowResult
from .runtime import event_origin
from .utils import first_text, normalize_sub_type


async def run_list_subscriptions(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    subscriptions = plugin.db.get_subscriptions(event_origin(event))
    sub_type = normalize_sub_type(first_text(request.params, "sub_type", "type") or "both")
    if sub_type in {"dynamic", "live"}:
        subscriptions = [sub for sub in subscriptions if sub.sub_type == sub_type]
    text = format_subscriptions(subscriptions)
    if not subscriptions:
        return WorkflowResult(text)
    return WorkflowResult(text, cards=[await subscription_list_card(plugin, subscriptions)])


async def run_list_all_subscriptions(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    return await run_list_subscriptions(plugin, event, _typed_request(request, "both"))


async def run_list_live_subscriptions(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    return await run_list_subscriptions(plugin, event, _typed_request(request, "live"))


async def run_list_dynamic_subscriptions(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    return await run_list_subscriptions(plugin, event, _typed_request(request, "dynamic"))


async def run_find_subscription(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    query = first_text(request.params, "query", "keyword", "target", "name") or request.target
    query = query.strip()
    if not query:
        return WorkflowResult("请提供要查找的 UP 名称、UID、标签或已确认简称。")

    sub_type = normalize_sub_type(first_text(request.params, "sub_type", "type") or "both")
    subscriptions = plugin.db.get_subscriptions(event_origin(event))
    if sub_type in {"dynamic", "live"}:
        subscriptions = [sub for sub in subscriptions if sub.sub_type == sub_type]

    matches = _filter_subscriptions(plugin, event_origin(event), subscriptions, query)
    text = format_subscriptions(matches)
    if not matches:
        return WorkflowResult(f"当前会话未找到与“{query}”匹配的订阅。")
    return WorkflowResult(text, cards=[await subscription_list_card(plugin, matches)])


async def run_account_status(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    accounts = await HttpClient.get_accounts()
    current_index = getattr(HttpClient, "_current_account_index", 0)
    text = format_accounts(accounts, current_index)
    if not accounts:
        return WorkflowResult(text)
    return WorkflowResult(text, cards=[account_status_card(accounts, current_index)])


async def run_diagnose_health(plugin, event, request: WorkflowRequest) -> str:
    accounts = await HttpClient.get_accounts()
    subscriptions = plugin.db.get_subscriptions()
    targets = plugin.db.get_targets()
    pending_count = len(await plugin.pending_store.list_tasks())
    return (
        "Bilibili 插件健康诊断：\n"
        f"- 数据库：{plugin.db.db_path}\n"
        f"- 订阅数：{len(subscriptions)}\n"
        f"- 会话数：{len(targets)}\n"
        f"- 账号数：{len(accounts)}\n"
        f"- 待处理事项：{pending_count}\n"
        f"- 动态检查间隔：{plugin.dynamic_check_interval}s\n"
        f"- 直播检查间隔：{plugin.live_check_interval}s\n"
        f"- 渲染器：{'已装配' if hasattr(plugin, 'renderer') else '未知'}"
    )


async def run_diagnose_resolver(plugin, event, request: WorkflowRequest) -> str:
    return format_resolver_stats(plugin)


async def run_check_status(plugin, event, request: WorkflowRequest) -> str:
    accounts = await HttpClient.get_accounts()
    browser_ready = "已配置系统 Chrome 回退" if hasattr(plugin, "renderer") else "未知"
    return (
        "Bilibili 插件诊断：\n"
        f"- 工作流：已启用\n"
        f"- AI 工具：已注册\n"
        f"- 账号数：{len(accounts)}\n"
        f"- 渲染器：{browser_ready}\n\n"
        f"{format_resolver_stats(plugin)}\n\n"
        + format_workflow_list()
    )


async def run_check_live_current_group(plugin, event, request: WorkflowRequest) -> str:
    target_id = event_origin(event)
    pushed = await plugin.scheduler.manual_live_check(target_id)
    return f"当前会话直播检查完成：推送 {pushed} 条。"


async def run_check_live_all_groups(plugin, event, request: WorkflowRequest) -> WorkflowResult:
    from .pending import store_pending_task

    task_id = await store_pending_task(
        plugin,
        event,
        request,
        kind="confirm_live_check_all",
        payload={},
    )
    return WorkflowResult(
        "已生成全部群直播检查确认任务，请引用确认卡回复“确认”或“取消”。",
        cards=[
            operation_confirm_card(
                title="确认检查全部群直播？",
                summary="这会读取全部启用直播订阅并触发 Bilibili 请求。确认后执行，取消则不检查。",
                username="全部群直播检查",
                uid="ALL",
            )
        ],
        task_id=task_id,
    )


async def execute_live_check_all(plugin, event) -> WorkflowResult:
    target_count, pushed = await plugin.scheduler.manual_live_check_all()
    return WorkflowResult(f"全部群直播检查完成：目标 {target_count} 个，推送 {pushed} 条。")


def _typed_request(request: WorkflowRequest, sub_type: str) -> WorkflowRequest:
    return WorkflowRequest(
        workflow=request.workflow,
        target=request.target,
        params={**request.params, "sub_type": sub_type},
        source=request.source,
    )


def _filter_subscriptions(plugin, target_id: str, subscriptions, query: str) -> list:
    normalized = normalize_alias(query)
    alias_uids = {
        item.get("uid")
        for item in plugin.db.find_up_aliases(query, target_id=target_id, limit=8)
    }
    matches = []
    for sub in subscriptions:
        fields = [sub.uid, sub.username, *list(sub.tags or [])]
        normalized_fields = [normalize_alias(field) for field in fields]
        if str(sub.uid) in alias_uids or any(normalized in field for field in normalized_fields):
            matches.append(sub)
    return matches
