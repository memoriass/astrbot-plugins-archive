# Bridge Channel Contract

Bridge Gateway 是外部通道、Codex relay、主动发送和后续 MCP discovery 的归一化边界。Gateway 可以发现外部能力和接收平台事件，但不能直接扩大 Plana Core authority。

## Normalized Incoming

外部消息进入 Core 前必须被收窄为 normalized metadata：

- `channel`: 外部平台或 adapter 名称。
- `session_id`: 稳定匿名 id，使用 hash 或本地映射，不传原始 token。
- `actor_id`: 归一化用户标识，仅用于 Core actor 线索。
- `payload_kind`: Core 已允许的 bridge kind。
- `capability_view`: Gateway 对该通道声明的能力视图。
- `rate_bucket`: 限流桶标识。

Gateway 应保留 human log 以便排障，但发给 Core/LLM 的 sliding history 只能包含必要片段。

## Capability Downgrade

外部平台能力必须先降级为 Core 已知 contract：

- `memory_query`
- `task_delegate`
- `result_report`
- `context_sync`
- `emotional_handoff`
- `workflow_request`

MCP discovery 只生成 canonical mapping。映射后的工具仍必须回到 Core capability registry、confirmation gate 和 audit；不得把 MCP tool id 直接作为 Core executor 能力。

## Ingress Rules

- 本机内联路径只允许 loopback；出现代理转发头时拒绝。
- 外部 gateway mode 必须有 token 和 rate limit。
- local secret、平台 token、runner token 只在 Gateway 内使用，不写入 Core payload。
- human log 与 LLM sliding history 分离，避免把完整平台日志塞入模型上下文。

## Event Relay

Codex relay 只负责提交、进度、结果、取消和 artifact 回传。状态回调可写入 Core workflow event ledger，但事件内容必须是 progress、artifact、submitted、result 或 failure，不能附带新执行权限。Runner contract 固定为 `plana.codex.runner.v1`，接口固定为 `/plana/codex/delegate`、`/plana/codex/result/{run_id}`、`/plana/codex/cancel/{run_id}` 和 `/plana/codex/artifact/{run_id}/{artifact_id}`。
# Runner Identity And Delivery Phases

Runner relay envelopes use a stable runner id, protocol version and bounded lane declarations. Network location is not execution identity. Delivery state is independently idempotent across submit, poll, callback, artifact, terminal and notification phases; a later notification failure cannot reverse a persisted terminal fact.

## Delivery Ownership

Bridge Gateway never sends Codex or registered-capability results to AstrBot sessions. Its responsibility ends after authenticated transport, normalization, artifact preparation, and successful Core result persistence. Core owns rendering, reply/mention policy, deduplication, and final message delivery. Bridge records the `notification_sent` value returned by Core only for transport audit and idempotency.
