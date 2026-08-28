# Plana Bridge Gateway

Plana Bridge Gateway 是 Plana Core 的独立传输边界。它不负责领域判断、审批或业务执行，只负责把受控消息和 Codex 任务送到正确端点，并将结果交回 Core。

## 当前职责

- 转发标准 Core bridge payload：`memory_query`、`result_report`、`context_sync`、`emotional_handoff`。
- 轮询并投递 Core proactive queue。
- 连接原生 `plana.codex.runner.v1` Runner，覆盖 delegate、result、cancel 和 artifact 生命周期。
- 可选转发 AstrBot 消息到 Nacho sidecar，并提供受 token 保护的主动发送入口。
- 通过同进程 `CoreInProcessAdapter` 优先访问 Core；HTTP URL 仅作为调试 fallback。

## 明确不负责

- 不注册任何 AstrBot LLM tool。
- 不持有 ANI-RSS、NCQQ、qBittorrent 或 Komga 凭据。
- 不执行领域 capability、shell、workflow、skill 或本地 command。
- 不审批 `OperationProposal`，不扩大 Core 授权范围。
- 不接受 delegate v2；非 v1 请求统一返回 `unsupported_delegate_version`。

## 关键配置

- `enabled`
- `internal_lan_mode` / `external_gateway_mode` / `api_token`
- `core_bridge_url` / `core_state_url`
- `core_proactive_poll_url` / `core_proactive_deliver_url`
- `enable_codex_runner` / `codex_runner_url`
- `codex_runner_id` / `codex_runner_lanes` / `codex_runner_protocol_version`
- `runner_access_policy`
- `codex_runner_submit_timeout_seconds` / `codex_runner_delivery_concurrency`
- `codex_result_callback_url`
- `enable_nacho_forward` 与主动发送配置

Runner token、Core token 等内部值由部署配置保存，不在公开 schema、日志或文档示例中输出。

## 验证

```powershell
python -m compileall -q .
python -m ruff check . --select F401,F811,F821,F841
python scripts/check_bridge_gateway.py
git diff --check
```

更完整的边界和生命周期说明见 `ARCHITECTURE.md` 与 `bridge/channel_contract.md`。
