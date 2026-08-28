# 配置说明

本文说明 `_conf_schema.json` 中的正式配置项。真实 API key、token、本地地址和测试日志不得写入仓库文档。

## Manager 配置

面板配置统一使用 `manager_profiles`。它在 AstrBot WebUI 中渲染为可增删的模板列表，每个条目代表一个 ncqq-manager 控制面板。

| 配置项 | 类型 | 说明 |
| --- | --- | --- |
| `default_manager` | `string` | 默认 manager ID，应匹配 `manager_profiles` 中的某个 `id`。 |
| `manager_profiles` | `template_list` | ncqq-manager 面板列表，每项包含 `id`、`name`、`manager_url`、`api_key`。 |

保存后的配置结构类似：

```json
{
  "default_manager": "local",
  "manager_profiles": [
    {
      "__template_key": "ncqq_manager",
      "id": "local",
      "name": "本地面板",
      "manager_url": "http://127.0.0.1:8080",
      "api_key": "..."
    },
    {
      "__template_key": "ncqq_manager",
      "id": "cloud",
      "name": "云端面板",
      "manager_url": "https://example.com",
      "api_key": "..."
    }
  ]
}
```

`id` 会被规范化为小写，只保留字母、数字、`-`、`_`；建议显式填写稳定 ID。聊天或调试命令中可写 `manager=cloud`，也可把实例写成 `cloud/mybot`。

## 二维码配置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `qrcode_private` | `bool` | `true` | 群聊触发二维码时，通过私聊发送给请求者。私聊失败时回退到群内直接展示。 |

## 通知配置

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_offline_notify` | `bool` | `true` | 启用定时掉线检测。 |
| `health_check_interval` | `int` | `5` | 掉线检测间隔，单位分钟。 |
| `notify_group` | `string` | 空 | 掉线和恢复通知推送群号；留空则不推送群通知。 |
| `enable_alert_webhook` | `bool` | `false` | 启动独立 HTTP 接收器，接收 ncqq-manager `plugin_api` 规则发出的掉线 POST。 |
| `alert_webhook_host` | `string` | `127.0.0.1` | POST 接收器监听地址。非 loopback 地址必须配置 token。 |
| `alert_webhook_port` | `int` | `6198` | POST 接收器监听端口。 |
| `alert_webhook_path` | `string` | `/ncqq-manager/alerts` | POST 接收路径。 |
| `alert_webhook_token` | `string` | 空 | POST 接收鉴权 token，可通过 query `token`、`Authorization: Bearer` 或 `X-NCQQ-Webhook-Token` 传入。 |

定时健康检查会遍历所有 configured manager。快照 key 使用 `manager/instance`，避免不同面板同名实例互相覆盖状态。

ncqq-manager 的 API 兜底通知对接方式：

1. 在插件配置中开启 `enable_alert_webhook`，设置监听地址、端口、路径和 token。
2. 在 ncqq-manager 告警设置中创建 `plugin_api` 规则，`webhook_url` 填入插件接收地址，例如：

```text
http://127.0.0.1:6198/ncqq-manager/alerts?manager=local&token=...
```

3. 在对应 QQ 通知规则中启用 API 兜底开关。ncqq-manager 只会在匹配的 QQ 通知规则允许 API 兜底时发送 `plugin_api` POST。

多 manager 场景建议在 URL query 中显式追加 `manager=<面板ID>`。`login_lost` payload 如包含 `dashboard_url`，插件也会尝试按 `manager_profiles[*].manager_url` 自动匹配；`instance_offline` payload 通常没有 dashboard 地址，因此应显式带 `manager`。

若 ncqq-manager 侧 URL 指向 `127.0.0.1`、内网 IP 或 AstrBot 所在机器，需要在 ncqq-manager 中允许本地 webhook 地址。插件收到 POST 后会写入同一个 `health_snapshot`，后续定时轮询不会对同一离线边沿重复告警。

## 群聊白名单

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_group_whitelist` | `bool` | `false` | 开启后只响应指定群聊。 |
| `response_groups` | `string` | 空 | 允许响应的群号，支持逗号、空格、顿号分隔。 |

白名单只限制群聊入口，不限制私聊。作用范围包括：

- LLM 工具入口 `ncqq_manager`
- `/ncqq` 调试命令
- 群内审批快捷回复

## 安全要求

- 文档和测试记录中只写示例 key，例如 `...`。
- 不提交真实 `manager_profiles`。
- 不把从远端复制的 AstrBot AI 配置写入仓库。
- 本地配置和接入测试记录放入 ignored 目录：`local-docs/` 或 `docs/current/`。
