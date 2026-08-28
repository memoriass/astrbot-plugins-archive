# Bridge Gateway 开源项目代码审计

审计日期：2026-07-12

## 1. 当前仓库基线

- 分支 `codex/bridge-gallery-split`，版本 `0.1.0-beta.1`，审计时有 18 个未提交项。
- `bridge/runtime.py` 负责装配；Core 正常走同进程 adapter，HTTP 只作为调试 fallback。
- Codex relay、proactive poll/delivery、credential provider、capability adapter 和 channel contract 已分模块，但 runtime 同时承担外部接入、主动投递、Runner relay 和调试 API。
- 安全姿态包含 loopback/token、LAN allowlist、active-send token、转发头拒绝和 delegate v2 capability fail-closed。
- 2026-07-12 验证：compileall、`scripts/check_bridge_gateway.py`、`git diff --check` 均通过；存在 LF/CRLF 转换提示。

## 2. 发现清单

### P0

- 无新增 P0 代码缺陷；但当前未提交开发态不能作为可复现发布版本。

### P1

1. **职责继续扩张。** channel ingress、Core adapter、主动发送、ANI-RSS adapter、Codex relay 和未来 MCP 都集中在一个插件，后续容易形成第二套 agent gateway。
2. **幂等模型没有统一成公开 contract。** Runner run id、Core task id、external event id 和主动发送重试存在，但提交、callback、poll、artifact 和 notification 没有统一 `idempotency_key` 生命周期。
3. **Runner 身份仍主要依赖网络位置。** LAN/private URL policy 能阻止公网误连，但 IP/host 不是稳定执行身份，无法表达 runner 能力、证书轮换、撤销和 lane ownership。
4. **callback 与 polling 的互斥和恢复需要状态机测试。** 当前生产使用 polling 合理，但重启后重复终态、callback 晚到、poll 先完成、artifact 部分失败等场景尚未被完整覆盖。
5. **artifact 传输与消息通知耦合较近。** 应保证 artifact 校验、Core 终态和主动通知分别幂等，任何一步失败不反转前一步的事实。

### P2

1. **channel capability 描述尚未产品化。** normalized channel contract 可以进一步暴露 rate limit、支持消息类型、附件上限和 delivery guarantees。
2. **缺少统一 dead-letter/重放视图。** 失败重试存在，但运营侧需要按 task/run/idempotency key 查看最后安全状态和人工重放资格。

## 3. 开源候选矩阵

| 项目 | 许可证/近期状态 | 可借鉴机制 | 依赖成本 | 裁决 |
| --- | --- | --- | --- | --- |
| `NousResearch/hermes-agent` | MIT；2026-07-11 推送；release `v2026.7.7.2` | 任务执行、事件、artifact、隔离 runner | 高，完整 agent 平台 | 仅保留 relay/runner 参考 |
| `modelcontextprotocol/python-sdk` | MIT；2026-07-10 推送；release `v1.28.1` | MCP transport、能力声明、结构化工具 contract | 中 | 未来只用于 Bridge discovery/adapter |
| Cyrene-Agent（本地） | 本地参考仓库 | Incoming/Outgoing contract、匿名 session、channel capability | 不作为依赖 | 适配其 contract 思路 |
| AstrBot（本地） | 宿主项目 | 平台 adapter、session、主动发送、Plugin API | 已有依赖 | 第一复用来源 |

官方来源：

- `https://github.com/NousResearch/hermes-agent`
- `https://github.com/modelcontextprotocol/python-sdk`

## 4. 深审结论

### 可直接借鉴

- Hermes 风格的 submitted/progress/artifact/terminal 顺序和 artifact 校验，但事件所有权仍在 Core/Bridge。
- MCP SDK 的 capability/schema 描述和 transport 生命周期，只用于生成受控 candidate。
- Cyrene 的 channel capability、匿名 session、human log 与 LLM history 分离。

### 需适配借鉴

- 统一 envelope：`task_id`、`run_id`、`idempotency_key`、`channel_id`、`runner_id`、`attempt`、`terminal_version`。
- Runner 注册只保存能力和身份声明；可执行 capability 仍必须与 Core registry 交集。
- dead-letter 重放必须重新检查 Core 状态，不能直接重复主动发送。

### 禁止引入

- Hermes 完整 gateway、shell、subagent、plugin market 或自主任务分解。
- MCP discovery 直接注册 executor 或扩大 Core allowlist。
- Bridge 建立独立 persona、provider、session 或持久聊天历史。

## 5. 目标架构与数据流

```text
channel adapter -> normalized ingress
                         |
                         v
                   Core policy/audit
                         |
          +--------------+-------------+
          v                            v
 controlled delivery relay      runner relay
          |                            |
          +---- idempotent events -----+
                         |
                   Core terminal state
                         |
                  notification relay
```

建议在现有仓库内先做模块拆分，不立即拆成多个发行插件。`runtime.py` 只装配 channel、delivery、runner 和 diagnostics 服务。

## 6. 实施任务

1. **统一幂等 envelope**：定义字段、生成规则和持久状态转换，覆盖 submit/callback/poll/artifact/notify。
2. **拆分 runtime 职责**：形成 channel ingress、delivery、runner relay、diagnostics 四个内部服务，保持现有 HTTP 路由兼容。
3. **Runner identity V1**：增加稳定 runner id、capabilities、lanes、protocol version 和认证材料引用；网络 allowlist 保留为第二层限制。
4. **终态竞态测试**：覆盖 callback/poll 乱序、重复 completed、late failure、Bridge/Core 重启和重复 notification。
5. **artifact 独立幂等**：校验 SHA-256、声明大小、路径 containment 和下载状态；通知失败不删除已验证 artifact。
6. **dead-letter 只读视图**：展示失败阶段、重试资格和恢复建议；人工重放前重新读取 Core 终态。
7. **MCP adapter spike**：只做 discovery 到 canonical candidate 的测试实现，不连接 executor。

验证：现有 check，加状态机 property tests、重复 callback、重启恢复、artifact 损坏、主动发送失败和 capability mismatch。

## 7. 最终裁决

- **立即实施**：统一幂等、终态竞态测试、artifact 独立状态、runtime 内部拆分。
- **验证后实施**：Runner identity 与 dead-letter 重放。
- **暂缓**：MCP transport 正式接入。
- **拒绝**：完整 Hermes gateway、任意终端执行、自动 MCP 授权和第二套会话系统。

## 8. 实施后复审（2026-07-12）

- 已新增持久 `DeliveryIdempotencyLedger`，覆盖终态 digest、相同结果重放、冲突终态拒绝和通知幂等。
- ledger 在插件初始化时建立，通知成功后持久标记，可跨 Bridge 重启保留。
- 专项测试覆盖 succeeded 重放、failed 冲突和重复通知标记。
- 已完成 Runner 非终态 observation：attempt、单调 event sequence、heartbeat lease 与取消握手经轮询转给 Core，重复 observation 不进入终态 ledger。
- 仍待完成：artifact 全阶段 envelope、Runner 认证身份轮换、callback/poll 并发集成测试和 dead-letter 运营视图。

## 9. 合并裁决实施

- Bridge 保持独立仓库，内部继续按 channel、delivery、runner relay 和 diagnostics 拆分，不再拆成额外发行插件。
- `DeliveryIdempotencyLedger` 已修复初始化 commit，并增加 submit/poll/callback/artifact/terminal/notification 阶段记录与冲突拒绝。
- Runner 配置新增稳定 `runner_id`、lane 声明和 protocol version；LAN allowlist 只作为第二层网络限制。
- 本地竞态测试覆盖 poll/callback 独立阶段、相同重放、冲突状态、artifact 和重复终态。
