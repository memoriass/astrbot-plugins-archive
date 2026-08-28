# Dialogue Proposal Handoff

Dialogue 不直接执行复杂任务，也不要求模型调用移交工具。

1. `DialogueService` 根据真实自然语言、上下文和当前领域 profile 判断聊天、领域插件或复杂任务。
2. 领域请求只挂载一个插件入口。
3. 复杂浏览器、代码、调查和长任务由 Core task broker 生成 bounded proposal。
4. `WorkflowContext.proposal_turn_context()` 只向 Core 本地 compiler 提供裁剪后的会话、资源范围和风险证据。
5. Core 生成 `PolicyDecision`、确认账本与 `ExecutionLease`；用户确认前不得提交 Runner。
6. Bridge 只转发 `plana.codex.runner.v1` bundle，结果回到原会话。

任何新字段都必须保持：模型不可确认自身 proposal、不可扩大资源范围、不可注入凭据、不可绕过本地 allowlist。
