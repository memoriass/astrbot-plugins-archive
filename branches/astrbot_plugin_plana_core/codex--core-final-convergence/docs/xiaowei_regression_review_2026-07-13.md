# Xiaowei-style Regression Review — 2026-07-13

## Evidence

- The replay set contains 50 redacted windows extracted from group `885617919`.
- Categories cover direct answers, service/search work, visual recommendations,
  corrections, follow-ups, artifact resend, cancellation, recovery and
  conservative proactive opportunities.
- Production ChatUI examples showed correct native qB queries and image-plus-
  text dinner recommendations, but also exposed formal execution narration and
  a duplicated rendered-card path.

## Fixed in this iteration

- Recommendation replies no longer render the same answer into an additional
  fallback card. A verified real image may accompany the normal text; if image
  resolution fails, the existing text is the only response.
- Structured task documents still use the external renderer because that path
  replaces the text result rather than duplicating it.
- The behavior prompt now suppresses repeated names, excessive honorifics,
  protocol narration, standby/command language and unnecessary closing
  questions.
- Daily sharing is treated as conversation content, not automatically converted
  into a task, maintenance request or execution-department report.
- A response-style reviewer records mechanical markers without rewriting the
  model response or changing permissions.

## Remaining gaps

- The selected AstrBot persona can still overpower temporary style guidance on
  some providers. Continue measuring actual responses before changing the
  global persona.
- Model latency and provider fallback can materially alter tone. Style scores
  must be compared by provider and should not be attributed only to Core.
- Proactive group participation still requires real QQ group validation; ChatUI
  cannot reproduce simultaneous speakers and reply-anchor ambiguity.
- A real image search result may be visually related but not the exact dish or
  title. Keep source validation and text-only fallback instead of forcing an
  approximate image.

## Acceptance additions

- No recommendation response contains both a generated card and the same full
  answer text.
- Ordinary chat contains at most one direct address and at most one honorific
  construction.
- Read-only results start with the result rather than tool or department
  narration.
- A completed ordinary task does not end with an unnecessary offer for more
  work.
- Daily sharing receives a natural acknowledgement without creating a task.
# 2026-07-13 ChatUI 复测补充

- 普通聊天与任务执行已拆分 prompt profile。普通聊天不再注入 `PLANA_STATE`、`TOOL_CONTEXT`、能力清单、Hermes 委派说明和超过四条的 Dialogue Ledger。
- 生产配置将 `dialogue_ledger_prompt_limit` 从 8 收敛到 4，`memory_inject_max_chars` 从 1800 收敛到 1000；操作性历史话术在进入 prompt 前过滤。
- 同一句“刚处理完一轮回归，有点累……”在旧 Persona 下回复为“检测到疲劳特征，请暂时中断工作线程”；收敛 `普拉娜v3` 后回复为“辛苦了，能把重复发送的问题解决掉就好。既然告一段落，先休息一会儿吧。”，说明人格指令是剩余机械感的主要来源。
- qB 只读状态复测不再暴露“内部服务网关/执行部门”，但真实工具返回 `service_capability_not_allowed`。该项属于能力注册或授权映射回归，与人格、记忆注入无关，不能用风格调整掩盖。
- 50 个真实小维窗口已重新从 `group_906678215_20260712_083826.json` 生成。当前完成的是场景集与静态行为检查；完整逐条真实 Core/model 回放仍应作为下一阶段独立评测任务，避免对生产端执行副作用。

## v4 记忆链收敛

- 生产默认 Persona 已切换为 `plana v4`。补充约束后，故障隐喻只用于真实复盘；普通聊天不再使用“分支、归零、损伤、挂起、监控状态”等表达。
- LivingMemory 保留消息存储、图记忆和显式 recall tool，但 `recall_engine.top_k=0`，停止与 Core 同时进行每轮自动注入。
- Core 实际嵌套配置修正为 `memory.memory_inject_max_chars=1000`、`persona_behavior.dialogue_ledger_prompt_limit=4`。
- `direct_answer` 与 `silence` 回复不再写入 Core 长期 LLM response、概念图和结构化事实；仅真实工具、artifact 和 Hermes 等任务结果进入结果记忆。
- 普通聊天 profile 不再调用 LLM 进行概念候选筛选。真实 ChatUI 中日常回复从“这个分支算是稳住了，我帮你看着状态”收敛为“零，辛苦了，能把问题解决就好。”；取消回复从“排查先挂起”收敛为“好，先不查了。”
