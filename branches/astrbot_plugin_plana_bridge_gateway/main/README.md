# Plana Bridge Gateway

Plana Bridge Gateway 是 Plana Core 的内网桥接与外部适配插件。默认部署在 AstrBot
同一进程内，优先直接调用 Core runtime；只有需要接入外部 bot、主动发送 API 或
Codex Runner 时才承担转发职责。

## 边界

- 默认 `internal_lan_mode=true`：Core/Bridge 走同进程调用，不需要 Core token 或 Astr `/api/plug` 鉴权头。
- `external_gateway_mode=false`：Bridge HTTP API 不作为公网入口；公网入口只由 AstrBot 提供。
- Codex Runner relay 只并发提交 `codex_delegate` payload，不执行任务、不写 Core、不审批 workflow/skill；单个 Runner 请求失败不会阻塞同批其它任务。
- 内网 Runner 的安全边界由私网地址校验和主机防火墙承担；Bridge 不再强制 Bearer token。
- Bridge 会在内网模式下自动领取 Core proactive 队列，不需要外部调用 `/api/plug` 推动 Codex 委派。
- Runner 拒绝零 worker lane 时，Bridge 保留 `lane_disabled:<lane>` 错误并把 Core 任务置为失败，不把禁用 lane 留在远端队列。
- Codex 终态先写入 Core；后续通知由 Core 统一负责，Bridge 只记录 Core 返回的通知状态。
- delegate v1 保持 Runner relay 兼容；delegate v2 只接受受控 `action` envelope，并由 Bridge capability adapter 执行。
- v2 只携带 `credential_ref`。Codex、Core payload 和日志都不接触原始 secret；adapter 在发起固定 API 请求前才解析凭据。

## 端点

| 端点 | 方法 | 用途 |
| --- | --- | --- |
| `/plana_bridge_gateway/status` | GET | Gateway 与 Core 状态探测 |
| `/plana_bridge_gateway/bridge` | POST | 调试用 bridge payload fallback |
| `/plana_bridge_gateway/proactive/poll-deliver` | POST | 调试用 proactive 领取与交付 |
| `/plana_bridge_gateway/codex/result` | POST | Runner 结果回流入口，仅允许 loopback 或配置的 Runner 主机 |
| `/plana_bridge_gateway/nacho/send` | POST | 可选主动发送入口 |

## 配置

- `internal_lan_mode`: 默认开启，使用同进程 Core adapter 和内网 Runner。
- `external_gateway_mode`: 默认关闭。只有 Bridge 需要直接对外提供 HTTP API 时开启。
- `api_token`: 仅外部网关模式使用。
- `core_*_url`: 仅同进程 Core 不可用时作为调试 fallback。
- `enable_codex_runner`: 是否把 Core proactive 队列中的 Codex 委派转发到 Runner。
- `codex_runner_url`: 内网 Runner 接收端点，例如 `http://192.168.1.202:8766/plana/codex/delegate`。
- Runner 必须实现 `plana.codex.runner.v1`，并提供 delegate、result、cancel 与 artifact 四类固定接口。
- `runner_access_policy`: 默认 `lan_allowlist`，只允许 loopback/private LAN Runner URL。
- `codex_runner_submit_timeout_seconds`: Runner 入队提交超时，默认 5 秒。
- `codex_runner_delivery_concurrency`: 每轮并发投递数，默认 4。
- `codex_result_callback_url`: 可选，仅在 callback 入口不受 Dashboard JWT 外层阻断且具备独立 Runner 鉴权时启用。为空时 Bridge 轮询 Runner，当前轮询窗口覆盖 120 秒任务超时。
- `proactive_poll_interval_seconds`: 自动领取 Core proactive 队列的间隔，默认 10 秒。
- `credential_store_directory`: 标准库认证加密凭据目录。Windows 使用 DPAPI 保护主密钥；Linux 使用 0700 目录和 0600 主密钥文件，无额外 Python 依赖。
- `enable_ani_rss_adapter`: 注册首版只读 `ani_rss.list_subscriptions` capability。
- `ani_rss_base_url` / `ani_rss_api_prefix`: ANI-RSS 固定内网地址与 API 前缀；delegate 不能传 URL、method、headers 或 body。
- `enable_komga_adapter`: 默认关闭的 legacy compatibility 开关。仅为仍使用旧 external delegate v2 contract 的调用方注册 Komga 三个只读 capability。
- `komga_base_url`: legacy shim 使用的 Komga 固定私网地址；external contract 不能覆盖 URL、凭据或 HTTP 方法。

## Komga Compatibility

Komga 的领域 descriptor、自然语言 proposal facade 与 `komga_manager` 工具由独立 Komga 插件提供。Bridge 不再公开 `komga_plugin` profile 或领域工具，避免重复 profile/tool 注册。

Bridge 仅保留 `komga.production` 下的 `komga.list_libraries`、`komga.search_series` 和 `komga.list_recent` 只读 adapter shim，供迁移期旧 external delegate v2 contract 使用。该 shim 默认关闭，不包含扫描、分析、刷新或其它写 capability。

ANI-RSS adapter 不返回原始订阅对象，只投影 `id`、`title/name`、`enable`、
`season`、`subgroup`、`progress/episode` 等用户可见标量字段。路径、URL、凭据、
匹配规则和其它完整 raw 数据都会丢弃；`count` 是过滤后总数，`returned_count` 是
当前 limit 实际返回数量。

delegate v2 形状固定为：

```json
{
  "type": "codex_delegate",
  "delegate_version": 2,
  "request_id": "request-id",
  "action": {
    "service_ref": "ani_rss.production",
    "capability": "ani_rss.list_subscriptions",
    "arguments": {"enabled": true, "limit": 50},
    "credential_ref": "ani-rss-main"
  }
}
```

首版 credential store 提供 `CredentialProvider.get/put/delete` 接口，但不暴露 HTTP
写入端点，避免 secret 出现在 URL、header、body、日志或宿主命令行。部署工具应在
Bridge 进程内调用 provider 写入，或由后续受确认保护的管理 UI 接入。

已有 ANI-RSS JSON 配置可通过本地导入脚本初始化。脚本参数只包含源文件路径和
credential store 目录；API key 从文件读取，不进入命令行或输出，源文件不会删除：

```powershell
python scripts\import_ani_rss_credential.py C:\secure\ani-rss.json C:\bridge-data\credentials
```

默认 credential ref 为 `ani_rss.production.api_key`，可通过 `--credential-ref` 修改。

当前 201/202 部署将该 callback 配置留空：201 的 `/api/plug/*` 需要 Dashboard JWT，202 直连会返回 401。Bridge 因此使用内网结果轮询；这不是回退到 201 执行。

## 验证

```powershell
python -m compileall -q .
python scripts\check_bridge_gateway.py
python scripts\check_domain_harness.py
git diff --check
```
