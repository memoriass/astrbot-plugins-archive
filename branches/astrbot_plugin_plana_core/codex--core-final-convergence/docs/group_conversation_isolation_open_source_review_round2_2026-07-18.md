# 群聊会话隔离开源方案调研（第二轮暂存）

状态：`draft_for_later_review`

日期：2026-07-18

本文件只保存第二轮开源项目调研结果，不代表 Core 最终架构决策，也不触发生产代码、数据库或 Web 改造。后续应与 NachoBot、MaiBot 调研结果合并后再评审。

## 调研目标

- 分离群公共上下文与成员私有任务状态。
- 稳定关联回复消息、线程根和当前任务。
- 隔离同一成员连续操作与其他成员插话。
- 支持重启、重试、中断和并发消息恢复。
- 不依赖 LLM 猜测任务归属或执行权限。

## 暂存结论

本轮没有发现单一项目可以直接复制到 Core。更成熟的实现普遍把会话拆成多个正交维度，而不是只使用一个 `session_id`：

1. 通道或群会话作用域。
2. 用户作用域。
3. 群内用户私有作用域。
4. 消息关系或线程根。
5. 任务运行及检查点命名空间。

对 Core 最有价值的新发现是 Microsoft Bot Framework 的 `PrivateConversationState`：它直接使用 `channel_id + conversation_id + user_id` 作为存储边界，与 Core 当前 `(scope_id, actor_id)` 的任务帧方向一致。Matrix 的线程根和 LangGraph 的检查点命名空间则分别补足消息锚点和运行恢复。

## Microsoft Bot Framework

Bot Framework 将状态拆成三个明确作用域：

- `ConversationState`：键为 `channel_id/conversations/conversation_id`，整个群或会话共享。
- `UserState`：键为 `channel_id/users/user_id`，用户跨会话共享。
- `PrivateConversationState`：键为 `channel_id/conversations/conversation_id/users/user_id/namespace`，只属于某个会话中的某个用户。

对 Core 的可迁移点：群近期消息进入 ConversationState 等价层；用户长期偏好进入 UserState 等价层；ANI 查询、字幕组选择和待确认操作进入 PrivateConversationState 等价层；namespace 继续区分 `ani`、`ncqq`、`workflow` 或独立任务。

限制：状态作用域本身没有消息线程根；同一成员在一个群中并行发起两个任务时仍需额外 `task_id`。官方 Python SDK 已归档，本轮只把它作为设计模式参考，不建议引入为运行依赖。

## Rasa

Rasa 使用 `sender_id` 获取、创建和保存 `DialogueStateTracker`，并在处理消息时按 `message.sender_id` 获取锁。Tracker 保存事件历史并支持恢复最新会话或完整历史。

对 Core 的可迁移点：同一状态机的事件使用稳定、可重建的复合身份；逻辑 sender key 可以定义为 `scope_id + actor_id + task_id`；按 sender key 加锁可以避免同一成员连续发送两条任务消息时并发覆盖状态。

限制：`sender_id` 是调用方定义的不透明键。如果把 QQ 群 ID 直接作为 `sender_id`，仍会产生当前 Core 相同的串话风险。Tracker 也不应承担能力授权和确认所有权。

## Matrix

Matrix 将消息关系显式存入事件：

- 线程事件使用 `m.relates_to.rel_type = m.thread`。
- 每条线程事件都指向固定 thread root，而不是只指向上一条消息。
- `m.in_reply_to.event_id` 单独表示本次回复的直接目标。
- 服务端按 thread root 聚合事件，并记录最新事件、事件数量和当前用户是否参与。

对 Core 的可迁移点：`thread_root_id` 映射为任务锚点；`reply_to_message_id` 表示本次引用目标；后续每轮直接携带根锚点；其他成员引用公开结果时可以加入同一公开 thread，但仍由 actor scope 决定是否创建自己的任务分支。

限制：QQ/AstrBot 不一定原生提供 thread root，需要 Core 自己维护映射。线程关系只能提供上下文归属，不能提供任务所有权或确认权限。

## Zulip

Zulip 的频道消息强制带 topic。消息模型同时保存 `recipient`、`subject`/topic 和 `sender`。Addressee 在频道消息没有 topic 时直接拒绝构造，而不是把消息全部混入频道主时间线。

对 Core 的可迁移点：群聊中的并行任务应拥有显式 topic；Core 可以内部生成不可见的 `task_topic_id`，隔离 ANI、NCQQ 和普通闲聊；topic 可以作为审计、Web 展示和任务恢复的稳定分类维度。

限制：QQ 用户不会主动选择 topic，Core 仍需通过回复锚点、实体引用和确认流程确定 topic。topic 权限键必须由 Core 生成，不能由 LLM 自由命名。

## LangGraph

LangGraph Checkpointer 使用 `thread_id` 作为检查点存取主键；内部任务进一步使用 `checkpoint_ns`、`task_id` 和 `checkpoint_id` 形成层级运行谱系。没有 thread ID 时，无法保存状态、从中断恢复或进行历史检查。

对 Core 的可迁移点：`thread_id` 映射为 Core `task_id`；`checkpoint_ns` 映射为 workflow、capability 或步骤路径；`checkpoint_id` 绑定每次尝试；中间写入绑定 task ID，避免 Runner 重试时重复提交已完成的副作用步骤。

限制：LangGraph 不负责判断某条群消息属于哪个 thread。如果入口选择了错误 thread ID，Checkpointer 只会稳定恢复错误上下文。它适合执行层恢复，不替代 actor 和 reply anchor 判断。

## 可供后续评审的组合模型

以下只是候选模型，不是本轮定案：

```text
PublicConversationScope
  key = platform + conversation_id

UserScope
  key = platform + actor_id

PrivateConversationScope
  key = platform + conversation_id + actor_id

TaskThread
  key = generated_task_id
  root_message_id = first_user_message_id or first_bot_result_message_id
  owner_actor_id = actor_id

MessageRelation
  message_id
  reply_to_message_id
  thread_root_message_id

ExecutionCheckpoint
  task_id
  checkpoint_namespace
  checkpoint_id
  attempt
```

| 层 | 保存内容 | 不允许承担 |
| --- | --- | --- |
| PublicConversationScope | 群近期公开消息、参与者、公开话题 | 确认权、取消权、私有任务参数 |
| UserScope | 用户稳定偏好和跨群身份 | 当前群任务状态 |
| PrivateConversationScope | 当前成员在当前群的焦点、候选、待确认状态 | 其他成员任务 |
| TaskThread | 任务目标、实体、owner、公开投影、状态 | 长期人格记忆 |
| MessageRelation | 回复目标和 thread root | 权限判断 |
| ExecutionCheckpoint | workflow 步骤、重试和完成记录 | 自然语言归属猜测 |

## 待下一轮统一评审的问题

1. 扩展现有 `assistant_conversation_frames`，还是新增明确的 PrivateConversationScope。
2. 是否新增 `assistant_message_anchors`，保存 Plana 消息到 task/thread 的映射。
3. 同一成员是否允许在同一群并行存在多个 active task。
4. 其他成员引用公开结果时，是创建 task fork，还是只创建新的只读上下文。
5. `TaskSessionState` 的 180 秒 TTL 是否只用于自然续接，TaskThread 是否需要更长生命周期。
6. 同一 `(scope_id, actor_id)` 是否需要类似 Rasa 的串行锁或乐观版本字段。
7. Codex Runner 重试是否使用 `task_id + namespace + checkpoint_id` 幂等键。
8. Web 是否分别显示群公共线程、成员任务分支和执行检查点。

## 来源快照

本轮以 2026-07-18 拉取到的官方仓库快照为准：

| 项目 | 官方仓库 | 检查提交 | 重点源码 |
| --- | --- | --- | --- |
| Bot Framework Python | `microsoft/botbuilder-python` | `e07ec54ed9a863b69a7cfae5162629383924709d` | `conversation_state.py`、`user_state.py`、`private_conversation_state.py` |
| Rasa | `RasaHQ/rasa` | `60a3cff9c08183760355b07bd60f5223d8916d6b` | `rasa/core/tracker_store.py`、`rasa/core/agent.py` |
| Matrix Specification | `matrix-org/matrix-spec` | `4c2bb5aae19dcb15e2bee3127d57de80b5068195` | `content/client-server-api/modules/threading.md` |
| Zulip | `zulip/zulip` | `7b3d58146f52c752c5d8cde3bd4e9ed0cd6daed0` | `zerver/models/messages.py`、`zerver/lib/addressee.py` |
| LangGraph | `langchain-ai/langgraph` | `49ae27c2ae983cfb92091b0dea9f7bc37a716479` | `libs/checkpoint/.../base/__init__.py`、`libs/langgraph/.../pregel/_algo.py` |

## 暂存边界

- 本轮没有修改 `dialogue/wake.py`、TaskSession、数据库 schema 或生产配置。
- 本轮没有部署到 201 或 202。
- 本轮没有将候选模型写入正式 `ARCHITECTURE.md`。
- 后续先读取本文件与 NachoBot/MaiBot 调研结果，再统一形成决策记录和实施计划。
