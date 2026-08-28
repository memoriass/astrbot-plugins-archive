"""Workflow ids, metadata, and request models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class WorkflowRequest:
    workflow: str
    target: str = ""
    manager_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "tool"


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    workflow: str
    title: str
    purpose: str
    admin_only: bool = False
    user_visible: bool = True


COMPILED_WORKFLOWS: dict[str, CompiledWorkflow] = {
    "manage_instance": CompiledWorkflow(
        workflow="manage_instance",
        title="实例主流程",
        purpose="按 intent 拼接创建、重登、控制、检测、列表、销毁等实例流程。",
    ),
    "query": CompiledWorkflow(
        workflow="query",
        title="查询主流程",
        purpose="按 scope 查询实例、后端、消息、审计、资源或配置。",
    ),
    "manage_backend": CompiledWorkflow(
        workflow="manage_backend",
        title="后端主流程",
        purpose="按 intent 查看后端端点或把后端接入实例。",
    ),
    "create_instance": CompiledWorkflow(
        workflow="create_instance",
        title="实例创建流程",
        purpose="创建或接续创建实例，按条件绑定用户、启动实例、接入后端、拉取二维码。",
        user_visible=False,
    ),
    "relogin_instance": CompiledWorkflow(
        workflow="relogin_instance",
        title="掉线重登流程",
        purpose="检查登录状态，离线时按条件拉取二维码。",
        user_visible=False,
    ),
    "control_instance": CompiledWorkflow(
        workflow="control_instance",
        title="实例控制流程",
        purpose="启动、停止、重启等生命周期操作，并按条件复查状态。",
        user_visible=False,
    ),
    "connect_backend": CompiledWorkflow(
        workflow="connect_backend",
        title="后端接入流程",
        purpose="校验后端别名和目标实例后，把已有端点接入实例。",
        user_visible=False,
    ),
    "check_instance": CompiledWorkflow(
        workflow="check_instance",
        title="实例检测流程",
        purpose="按实例存在、登录、资源、日志顺序排查问题。",
        admin_only=True,
        user_visible=False,
    ),
    "list_instances": CompiledWorkflow(
        workflow="list_instances",
        title="实例列表流程",
        purpose="查看实例状态与绑定关系。",
        user_visible=False,
    ),
    "check_backends": CompiledWorkflow(
        workflow="check_backends",
        title="后端端点检测流程",
        purpose="查看已配置后端端点，不显示 token 明文。",
        user_visible=False,
    ),
    "read_bot_messages": CompiledWorkflow(
        workflow="read_bot_messages",
        title="Bot 消息读取流程",
        purpose="读取指定 Bot 的最近消息缓存。",
        admin_only=True,
        user_visible=False,
    ),
    "audit_operations": CompiledWorkflow(
        workflow="audit_operations",
        title="操作审计流程",
        purpose="读取最近操作日志，排查谁做过什么变更。",
        admin_only=True,
        user_visible=False,
    ),
    "inspect_resources": CompiledWorkflow(
        workflow="inspect_resources",
        title="资源检测流程",
        purpose="查看管理器镜像和节点资产。",
        admin_only=True,
        user_visible=False,
    ),
    "read_instance_config": CompiledWorkflow(
        workflow="read_instance_config",
        title="配置读取流程",
        purpose="查看实例文件树和指定配置文件摘要。",
        admin_only=True,
        user_visible=False,
    ),
    "delete_instance": CompiledWorkflow(
        workflow="delete_instance",
        title="实例销毁流程",
        purpose="显式确认后删除实例，并复用审批与解绑逻辑。",
        user_visible=False,
    ),
    "review_approvals": CompiledWorkflow(
        workflow="review_approvals",
        title="审批队列流程",
        purpose="查看待审批的高权限流程请求。",
        admin_only=True,
    ),
}

_ACTION_ALIASES: dict[str, str] = {
    "start": "start",
    "启动": "start",
    "stop": "stop",
    "停止": "stop",
    "restart": "restart",
    "reboot": "restart",
    "重启": "restart",
    "pause": "pause",
    "暂停": "pause",
    "unpause": "unpause",
    "resume": "unpause",
    "恢复运行": "unpause",
    "kill": "kill",
    "强杀": "kill",
}

_LIFECYCLE_ACTIONS = {"start", "stop", "restart", "pause", "unpause", "kill"}
_APPROVAL_ACTION_ALIASES: dict[str, str] = {
    "": "list",
    "list": "list",
    "ls": "list",
    "show": "list",
    "查看": "list",
    "列表": "list",
    "approve": "approve",
    "yes": "approve",
    "ok": "approve",
    "批准": "approve",
    "同意": "approve",
    "通过": "approve",
    "reject": "reject",
    "no": "reject",
    "cancel": "reject",
    "拒绝": "reject",
    "驳回": "reject",
    "否决": "reject",
}
