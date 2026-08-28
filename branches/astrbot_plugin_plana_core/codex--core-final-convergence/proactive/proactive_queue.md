# Proactive Queue

`proactive/` 维护 Core 内部主动任务队列。Core 只创建、查看、取消和标记交付状态，不直接发送平台消息。

## 文件职责

- `queue.py`: SQLite-backed proactive task queue。
- `schedule_parser.py`: 常见提醒/预约时间短语解析，返回候选 timestamp。

## 数据流

1. 已确认 workflow 或 Web API 写入 proactive task。
2. Core Dashboard 可查看和取消 pending/retry/in-flight 任务。
3. Bridge Gateway 通过 `/plana_core/bridge/proactive/poll` 领取到期 payload；队列会以 lease 语义把任务从 `pending/retry_pending` 标为 `in_flight`，写入 `attempts`、`locked_until`、`lane`。
4. Bridge/外部 bot 交付成功后调用 `/plana_core/bridge/proactive/deliver` 标记 `delivered`，失败则写入 `last_error` 并按指数退避回到 `retry_pending`；超过尝试上限才进入 `failed`。

## 触发解释字段

主动任务可携带：

- `trigger_reason`: 触发原因，例如 workflow step、自然语言提醒解析或 Codex 委派。
- `trigger_scene`: 触发时的入口面或场景。
- `effective_capability_view_hash`: 触发时 Core 看到的能力视图 hash。

这些字段只用于 Dashboard、审计和后续质量分析，不授予新执行权限，也不改变 lease/retry 行为。

## 维护规则

- 队列只保存待交付 payload 和交付 lease/retry 状态，不保存外部 bot 会话状态。
- 历史 `ready` 状态在初始化时迁移为 `pending`；当前租约模型只从 `pending/retry_pending` 进入 `in_flight`。
- Codex 委派使用固定 lane：`interactive`、`long`、`high_isolation`、`import`。Core 只写入 lane 元数据；并发执行由 Bridge/Runner 负责。
- Codex payload 内的 `delivery_context` 是任务创建时冻结的投递契约。队列、Bridge 和 Runner 只能原样传递；终态回传中的 scope、actor 或接收者不能扩大或替换 Core 已保存的目标。
- 时间解析只产出候选值；持久化写入仍必须走确认边界。
- 新主动任务类型必须同步 workflow capability、Web 展示和验证脚本。
