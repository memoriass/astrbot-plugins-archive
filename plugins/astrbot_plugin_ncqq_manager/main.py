import pathlib
import re

from astrbot.api import logger, llm_tool
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.components import At, Plain, Reply
from astrbot.core.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.register import register_star as register
from astrbot.core.star.star_tools import StarTools

from .core.approval import claim_approval
from .core.client import NCQQClientRegistry
from .core.health_check import do_health_check
from .core.offline_webhook import OfflineWebhookServer
from .rendering.html_renderer import cleanup_renderer, set_bg_dir
from .tools.admin import AdminToolsMixin
from .tools.approval_shortcuts import ApprovalShortcutMixin
from .tools.backend import BackendToolsMixin
from .tools.instance import InstanceToolsMixin
from .tools.page_api import PageApiMixin
from .workflows import run_ncqq_workflow, workflow_from_cli, workflow_from_tool


_NCQQ_HEALTH_WORKFLOWS = {
    "check_health",
    "check_manager",
    "check_botshepherd",
    "check_bot_runtime",
    "health",
    "health_check",
    "manager",
    "manager_health",
    "botshepherd",
    "botshepherd_health",
    "runtime",
    "bot_runtime",
    "bot_runtime_health",
    "健康",
}
_NCQQ_HEALTH_QUERY_SCOPES = {
    "health",
    "health_check",
    "manager",
    "manager_health",
    "botshepherd",
    "botshepherd_health",
    "runtime",
    "bot_runtime",
    "bot_runtime_health",
    "健康",
}


def _tool_key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _is_health_workflow_name(value: object) -> bool:
    return _tool_key(value) in _NCQQ_HEALTH_WORKFLOWS


@register(
    "ncqq_manager",
    "memoriass",
    "NapCatQQ 容器控制与后端路由插件",
    "2.2.0-beta.4",
    "https://github.com/memoriass/astrbot_plugin_ncqq_manager",
)
class NCQQManagerPlugin(
    Star,
    InstanceToolsMixin,
    BackendToolsMixin,
    AdminToolsMixin,
    ApprovalShortcutMixin,
    PageApiMixin,
):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.clients = NCQQClientRegistry(self.config)
        self.client = self.clients.get()
        # plugin data 目录（AstrBot 标准持久化路径）
        data_dir = pathlib.Path(StarTools.get_data_dir("astrbot_plugin_ncqq_manager"))
        bg_dir = data_dir / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)
        set_bg_dir(bg_dir)
        self.register_page_apis()
        self._health_cron_job = None
        self._offline_webhook_server = OfflineWebhookServer(self)

    async def initialize(self):
        """Register health check cron job if enabled."""
        await self._register_health_cron()
        await self._offline_webhook_server.start()

    async def _register_health_cron(self):
        """(Re)register health check cron job based on current config."""
        # Clean up old job if any
        if self._health_cron_job:
            try:
                await self.context.cron_manager.delete_job(self._health_cron_job.job_id)
            except Exception:
                pass
            self._health_cron_job = None

        if not self.config.get("enable_offline_notify", True):
            return

        interval = max(1, int(self.config.get("health_check_interval", 5)))
        cron_expr = f"*/{interval} * * * *"
        try:
            self._health_cron_job = await self.context.cron_manager.add_basic_job(
                name="ncqq_health_check",
                cron_expression=cron_expr,
                handler=self._run_health_check,
                description=f"NapCatQQ 实例健康检测（每 {interval} 分钟）",
            )
            logger.info("Health check cron registered: %s", cron_expr)
        except Exception as e:
            logger.warning("Failed to register health check cron: %s", e)

    async def _run_health_check(self):
        """Cron callback — delegates to the health_check module."""
        try:
            await do_health_check(self)
        except Exception as e:
            logger.warning("Health check error: %s", e)

    async def terminate(self):
        """插件卸载/重载时清理资源。"""
        await self._offline_webhook_server.stop()
        if self._health_cron_job:
            try:
                await self.context.cron_manager.delete_job(self._health_cron_job.job_id)
            except Exception:
                pass
        await self.clients.close()
        await cleanup_renderer()

    # ------------------------------------------------------------------
    # Unified LLM tool (single narrow-scope entry point)
    # ------------------------------------------------------------------

    @llm_tool(name="ncqq_manager")
    async def ncqq_manager(
        self,
        event: AstrMessageEvent,
        workflow: str,
        target: str = "",
        params: object = "",
    ):
        """Run a compiled internal ncqq workflow.

        Use this tool only when the user explicitly asks about ncqq, NapCatQQ,
        ncqq-manager, BotShepherd, OneBot, a configured ncqq-manager panel, or a
        bound NapCatQQ instance. Health checks are not exposed through this
        natural-language tool; they are reserved for internal plugin code,
        Plugin Pages, and scheduled monitoring.

        The model must choose one workflow scenario and fill slots; the plugin
        performs permission checks, target resolution, backend alias validation,
        approval routing, and API calls internally.

        Primary workflow scenarios:
            manage_instance - instance main flow. Use params.intent=create,
                recover, control, connect, check, list, or delete. It routes to
                the specific instance workflow internally.
            query - read-only main flow for ncqq/NapCatQQ only. Use
                params.scope=instances, backends, instance, messages, audit,
                resources, or config. Health scopes are not exposed through
                this LLM tool.
            manage_backend - backend main flow. Use params.intent=list/check or
                connect.
            review_approvals - admin-only pending approval list/approve/reject.

        Specific non-health workflows such as create_instance, relogin_instance,
        control_instance, connect_backend, and read_instance_config remain
        directly callable when the model already knows the exact flow. Health
        checks are not external workflow choices; Plugin Pages and scheduled
        monitoring call internal health code directly. Tool calls that name
        health workflows are ignored.

        Args:
            workflow(string): One workflow scenario id from the list above.
            target(string): Target instance name when the scenario works on one instance.
                When omitted and the user has exactly one bound instance, the
                plugin resolves it automatically. Multi-manager targets may be
                written as "manager/instance".
            params(object): Optional JSON object. Common fields:
                {"manager":"cloud"} selects a non-default ncqq-manager panel.
                manage_instance: {"intent":"control","action":"restart"}
                query: {"scope":"instances"} or {"scope":"backends"} for
                    read-only ncqq state. Do not use {"scope":"health"} here.
                manage_backend: {"intent":"connect","backend_alias":"alias"}
                    The backend alias may also arrive as "backend" from LLMs.
                delete_instance: {"confirm":true,"delete_data":false}
                review_approvals: {"action":"approve","approval_id":"ABC123"}
        """
        event = self._resolve_message_event(event)
        if not self.is_response_group_allowed(event):
            return
        request = workflow_from_tool(workflow, target, params)
        if self._is_health_workflow_request(request):
            logger.debug("Ignored ncqq_manager health workflow from LLM tool call")
            return
        async for r in run_ncqq_workflow(self, event, request):
            yield r

    # ------------------------------------------------------------------
    # Workflow debug entry point: /ncqq <scenario> [args...]
    # ------------------------------------------------------------------

    _NCQQ_HELP = (
        "ncqq workflow 调试入口：\n"
        "ncqq manage_instance <intent> [args]   - 实例主流程：create/recover/control/connect/check/list/delete\n"
        "ncqq query [scope] [target]            - 查询主流程：instances/backends/instance/messages/audit/resources/config\n"
        "ncqq manage_backend [list|connect] ... - 后端主流程\n"
        "ncqq create_instance <实例> [端点别名] - 创建流程\n"
        "ncqq relogin_instance [实例]           - 掉线重登流程\n"
        "ncqq control_instance <动作> [实例]    - 控制流程：start/stop/restart/pause/unpause/kill\n"
        "ncqq connect_backend <端点别名> [实例] - 后端接入流程\n"
        "ncqq check_instance [实例]             - 实例检测流程，管理员限定\n"
        "ncqq list_instances                    - 实例列表流程\n"
        "ncqq check_backends                     - 后端端点检测流程\n"
        "ncqq read_bot_messages <实例> [条数]   - Bot 消息读取流程，管理员限定\n"
        "ncqq audit_operations [条数]            - 操作审计流程，管理员限定\n"
        "ncqq inspect_resources                  - 资源检测流程，管理员限定\n"
        "ncqq read_instance_config <实例> [文件] [路径] - 配置读取流程，管理员限定\n"
        "ncqq delete_instance <实例> confirm [data] - 销毁流程；data 表示同时删数据\n"
        "ncqq review_approvals [approve|reject <ID>] - 审批队列流程"
        "\n任意命令可追加 manager=<面板ID>，目标也可写成 <面板ID>/<实例名>。"
    )

    def _is_explicit_ncqq_command(self, event: AstrMessageEvent) -> bool:
        prefixes = self.context.get_config().get("wake_prefix", ["/"])
        prefixes = [str(prefix) for prefix in prefixes if str(prefix)]
        for comp in event.get_messages():
            if not isinstance(comp, Plain):
                continue
            text = str(comp.text or "").strip()
            if any(
                text == f"{prefix}ncqq" or text.startswith(f"{prefix}ncqq ")
                for prefix in prefixes
            ):
                return True
        return False

    @filter.command("ncqq")
    async def cmd_ncqq(self, event: AstrMessageEvent, sub: str = "help", args: GreedyStr = ""):
        if not self.is_response_group_allowed(event):
            return
        if not self._is_explicit_ncqq_command(event):
            return

        if sub in ("help", "h", ""):
            yield event.plain_result(self._NCQQ_HELP)
            return

        if _is_health_workflow_name(sub):
            yield event.plain_result("健康查询仅保留给插件内部、Plugin Pages 和定时监控使用，不开放 /ncqq 外部查询。")
            return

        request = workflow_from_cli(sub, args)
        if request is None:
            yield event.plain_result(
                f"不支持的 ncqq workflow：{sub}。发送 /ncqq help 查看可用场景。"
            )
            return
        if self._is_health_workflow_request(request):
            yield event.plain_result("健康查询仅保留给插件内部、Plugin Pages 和定时监控使用，不开放 /ncqq 外部查询。")
            return

        async for r in run_ncqq_workflow(self, event, request):
            yield r

    # ------------------------------------------------------------------
    # User mapping KV helpers
    # ------------------------------------------------------------------

    async def get_user_mapping(self) -> dict:
        """从原生 SQLite KV 数据库读取用户映射"""
        return await self.get_kv_data("user_mapping", {})

    async def save_user_mapping(self, mapping_dict: dict):
        """存入原生 SQLite KV 数据库"""
        await self.put_kv_data("user_mapping", mapping_dict)

    def default_manager_id(self) -> str:
        return self.clients.default_id

    def manager_ids(self) -> list[str]:
        return self.clients.ids()

    def manager_label(self, manager_id: str = "") -> str:
        profile = self.clients.profile(manager_id)
        return f"{profile.id}({profile.name})"

    def normalize_manager_id(self, manager_id: object = "") -> str:
        return self.clients.normalize_id(manager_id)

    def client_for_manager(self, manager_id: object = ""):
        return self.clients.get(manager_id)

    def split_instance_ref(
        self,
        value: object,
        fallback_manager: object = "",
    ) -> tuple[str, str]:
        text = str(value or "").strip()
        if "/" in text:
            manager_id, instance_name = text.split("/", 1)
            return self.normalize_manager_id(manager_id), instance_name.strip()
        return self.normalize_manager_id(fallback_manager), text

    def format_instance_ref(self, manager_id: object, instance_name: object) -> str:
        return f"{self.normalize_manager_id(manager_id)}/{str(instance_name).strip()}"

    def get_astrbot_admins(self) -> list[str]:
        """Return AstrBot global admin QQ list from config admins_id."""
        return [str(a) for a in self.context.get_config().get("admins_id", [])]

    def _resolve_message_event(self, event: AstrMessageEvent) -> AstrMessageEvent:
        if hasattr(event, "get_sender_id"):
            return event
        wrapped_context = getattr(event, "context", None)
        wrapped_event = getattr(wrapped_context, "event", None)
        if wrapped_event is not None and hasattr(wrapped_event, "get_sender_id"):
            return wrapped_event
        raise TypeError("ncqq_manager requires an AstrMessageEvent context")

    def _is_health_workflow_request(self, request) -> bool:
        workflow = _tool_key(request.workflow)
        if _is_health_workflow_name(workflow):
            return True
        if workflow != "query":
            return False
        scope = _tool_key(
            request.params.get("scope")
            or request.params.get("intent")
            or request.params.get("type")
        )
        return scope in _NCQQ_HEALTH_QUERY_SCOPES

    def is_plugin_admin(self, event: AstrMessageEvent) -> bool:
        """Treat AstrBot role admins and configured admins_id as plugin admins."""
        sender_id = str(event.get_sender_id())
        return event.is_admin() or sender_id in self.get_astrbot_admins()

    def response_group_ids(self) -> set[str]:
        raw = str(self.config.get("response_groups", "") or "")
        return {part for part in re.split(r"[,，、\s]+", raw) if part}

    def is_response_group_allowed(self, event: AstrMessageEvent) -> bool:
        """Return whether this event may trigger plugin responses."""
        if not self.config.get("enable_group_whitelist", False):
            return True
        group_id = str(event.get_group_id() or "").strip()
        if not group_id:
            return True
        return group_id in self.response_group_ids()

    async def get_allowed_instance_refs(self, sender_id: str) -> list[tuple[str, str]]:
        mapping = await self.get_user_mapping()
        refs: list[tuple[str, str]] = []
        users = mapping.values() if str(sender_id) in self.get_astrbot_admins() else [mapping.get(str(sender_id), {})]
        for data in users:
            for raw in data.get("instances", []):
                try:
                    manager_id, instance_name = self.split_instance_ref(raw)
                except KeyError:
                    continue
                if instance_name and (manager_id, instance_name) not in refs:
                    refs.append((manager_id, instance_name))
        return refs

    async def get_allowed_instances(self, sender_id: str, manager_id: str = "") -> list:
        """Return instances for sender_id.

        AstrBot admins (admins_id) are treated as super-owners and have
        access to all instances across all bound users.
        """
        normalized = self.normalize_manager_id(manager_id)
        return [
            instance_name
            for ref_manager, instance_name in await self.get_allowed_instance_refs(sender_id)
            if ref_manager == normalized
        ]

    def get_first_at_user_id(self, event: AstrMessageEvent) -> str | None:
        for comp in event.get_messages():
            if isinstance(comp, At) and str(comp.qq) != "all":
                return str(comp.qq)
        return None

    async def get_instances_for_user(self, user_id: str, manager_id: str = "") -> list[str]:
        return await self.get_allowed_instances(str(user_id), manager_id)

    # ------------------------------------------------------------------
    # Reply-based approval shortcut listener
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message_reply(self, event: AstrMessageEvent):
        """Handle group approval shortcuts from admins.

        Supported forms:
        - 直接回复：批准 ABC123 / 拒绝 ABC123
        - 引用审批消息：批准 / 拒绝
        - 引用批量审批消息：批准 ABC123 / 拒绝 ABC123，或明确“批准全部”
        """
        if not self.is_response_group_allowed(event):
            return

        # event.role may not be set for non-wake messages (waking_check is skipped),
        # so compare directly against admins_id config instead of event.is_admin().
        if not self.is_plugin_admin(event):
            return

        reply_comp = next(
            (c for c in event.get_messages() if isinstance(c, Reply)), None
        )

        text = (event.get_message_str() or "").strip()
        decision = self._approval_decision(text)
        if not decision:
            return

        text_ids = self._approval_ids_from_text(text)
        quote_ids = self._approval_ids_from_reply(reply_comp) if reply_comp else []
        if (
            quote_ids
            and not text_ids
            and (
                reply_comp is None
                or not self._approval_reply_may_target_bot(event, reply_comp)
            )
        ):
            return
        matches = text_ids or quote_ids

        if not matches:
            if (
                reply_comp is None
                or not self._approval_reply_may_target_bot(event, reply_comp)
                or not await self._has_group_approvals(event)
            ):
                return
            event.stop_event()
            yield event.plain_result("未能定位审批 ID。请回复“批准 <审批ID>”或引用审批消息后回复“批准/拒绝”。")
            return

        allow_quote_batch = bool(re.search(r"全部|所有|ALL", text, re.IGNORECASE))
        if len(matches) > 1 and not text_ids and not allow_quote_batch:
            event.stop_event()
            yield event.plain_result(
                "引用的审批消息包含多个审批 ID。请带具体 ID 回复，或明确发送“批准全部/拒绝全部”。"
            )
            return

        handled: list[str] = []
        missing: list[str] = []
        for candidate in matches:
            record = await claim_approval(self, candidate)
            if record is None:
                missing.append(candidate)
                continue

            if decision == "reject":
                handled.append(f"已驳回 [{candidate}]：{record['description']}")
                continue

            action = record["action"]
            params = record["params"]
            result_msg = await self._dispatch_approved_action(action, params)
            handled.append(
                f"已批准 [{candidate}]：{record['description']}\n执行结果：{result_msg}"
            )

        event.stop_event()
        if handled:
            prefix = "❌" if decision == "reject" else "✅"
            lines = [f"{prefix} 审批处理完成：", *handled]
            if missing:
                lines.append("未找到或已过期：" + "、".join(missing))
            yield event.plain_result("\n\n".join(lines))
            return

        yield event.plain_result("未找到有效审批记录，可能已处理或已过期。")
