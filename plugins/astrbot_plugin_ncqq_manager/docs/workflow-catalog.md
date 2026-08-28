# Workflow Catalog

本文记录聊天侧可选 workflow、选择规则和 `/ncqq` 调试命令。实现细节见 `docs/workflow-engine.md`。

## 主 Workflow

| workflow | 能力方向 | 说明 |
| --- | --- | --- |
| `manage_instance` | 实例主流程 | 根据 `intent` 路由到创建、重登、控制、接后端、检测、列表、销毁。 |
| `query` | 查询主流程 | 根据 `scope` 路由到 ncqq 实例、后端、消息、审计、资源、配置查询。 |
| `manage_backend` | 后端主流程 | 根据 `intent` 查看后端端点或接入后端。 |
| `review_approvals` | 审批队列流程 | 管理员查看、批准或驳回待审批请求。 |

## 细分 Workflow

细分入口可直接调用，但聊天场景优先选择主 workflow。健康能力不注册为 workflow；Plugin Pages 和定时监控直接调用内部健康代码。

| workflow | 来源 | 说明 |
| --- | --- | --- |
| `create_instance` | `manage_instance intent=create` | 创建实例，可选绑定用户、启动、接入后端和拉取二维码。 |
| `relogin_instance` | `manage_instance intent=recover` | 检查登录状态，必要时拉取二维码。 |
| `control_instance` | `manage_instance intent=control` | 执行 start/stop/restart/pause/unpause/kill。 |
| `connect_backend` | `manage_instance intent=connect` 或 `manage_backend intent=connect` | 把已有后端端点接入实例。 |
| `check_instance` | `query scope=instance` | 检测实例存在、登录、资源、日志和可选配置。 |
| `list_instances` | `query scope=instances` | 查看实例状态和绑定关系。 |
| `check_backends` | `query scope=backends` | 查看后端端点，不展示 token 明文。 |
| `read_bot_messages` | `query scope=messages` | 管理员读取指定 Bot 最近消息缓存。 |
| `audit_operations` | `query scope=audit` | 管理员读取最近操作日志。 |
| `inspect_resources` | `query scope=resources` | 管理员查看镜像和节点资产。 |
| `read_instance_config` | `query scope=config` | 管理员查看实例文件树和配置摘要。 |
| `delete_instance` | `manage_instance intent=delete` | 显式确认后删除实例，普通用户进入审批。 |

## 选择规则

| 用户意图 | 选择 workflow |
| --- | --- |
| 创建实例、开通 bot、给某人开通 | `manage_instance`，`intent=create` |
| 掉线、重新登录、获取二维码、扫码 | `manage_instance`，`intent=recover` |
| 重启、启动、停止、暂停 | `manage_instance`，`intent=control`，带 `action` |
| 把某个后端接到实例上 | `manage_backend`，`intent=connect` |
| 实例有什么问题、看日志、资源占用 | `query`，`scope=instance` |
| 有哪些实例、当前状态 | `query`，`scope=instances` |
| 有哪些后端端点 | `query`，`scope=backends` |
| 看某个 Bot 最近消息 | `query`，`scope=messages` |
| 谁操作过、最近变更 | `query`，`scope=audit` |
| 有哪些镜像或节点资源 | `query`，`scope=resources` |
| 看配置或文件 | `query`，`scope=config` |
| 删除或销毁实例 | `manage_instance`，`intent=delete` |
| 查看、批准或拒绝审批 | `review_approvals` |

## 多 Manager 参数

工具参数支持 `manager`、`manager_id`、`panel`、`site`：

```json
{
  "workflow": "manage_instance",
  "target": "mybot",
  "params": {
    "manager": "cloud",
    "intent": "control",
    "action": "restart"
  }
}
```

等价目标写法：

```text
/ncqq manage_instance control restart cloud/mybot
/ncqq manage_backend connect astrbot cloud/mybot
```

## 调试命令

```text
ncqq manage_instance <intent> [args]
ncqq query [scope] [target]
ncqq manage_backend [list|connect] ...
ncqq create_instance <实例> [端点别名]
ncqq relogin_instance [实例]
ncqq control_instance <start|stop|restart|pause|unpause|kill> [实例]
ncqq connect_backend <端点别名> [实例]
ncqq check_instance [实例]
ncqq list_instances
ncqq check_backends
ncqq read_bot_messages <实例> [条数]
ncqq audit_operations [条数]
ncqq inspect_resources
ncqq read_instance_config <实例> [文件] [路径]
ncqq delete_instance <实例> confirm [data]
ncqq review_approvals [approve|reject <审批ID>]
```

任意命令尾部可追加 `manager=<面板ID>`。目标实例也可直接写成 `<面板ID>/<实例名>`。
