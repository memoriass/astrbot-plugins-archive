# P45 Hermes 对话核心与 Workflow Center 二期计划

## 结论

继续保留 `astrbot_plugin_plana_core` 与
`astrbot_plugin_plana_workflow_center` 的拆分，但把它定义为软拆分：

- Core 必须可独立运行。
- Workflow Center 只负责 proposal，不执行副作用、不持有确认权、不写 Core 数据库。
- Core 调用 Center 是可选增强；Center 不可用时按配置选择 fallback 或拒绝自然语言 draft。
- 如果后续 Center 没有独立模型链、skill/recipe 检索、proposal 缓存或独立验证价值，应回收为 Core 内部 `workflows/proposal/` 模块。

当前阶段不建议合并。原因是 Workflow Center 仍是变化最快的区域，保留拆分可以把 proposal 试验、复杂多模型顾问链和未来 skill 检索隔离在执行边界之外。

## Hermes 参考边界

参考 Hermes Agent 的方向是治理抽象，不是复制平台：

- 对话入口、外部 gateway、tool registry、toolsets、skills、executor 后端要分层。
- 模型只能看到收窄后的 toolset view。
- Proposal 和 execution 分离。
- approval、allowlist、scan、redaction 是治理层，不是 OS sandbox。
- 执行权必须落在本地受控 registry、compiler、confirmation gate 和 executor。

映射到 Plana：

| Hermes 抽象 | Plana Core | Workflow Center |
| --- | --- | --- |
| Agent dialogue loop | `dialogue/` 对话核心，负责事件转译、路由、prompt policy | 不接管普通对话 |
| Gateway / platform registry | `workflows/surfaces.py` 与 AstrBot command/Web/Bridge/LLM tool 映射 | 只接受 Core 认证请求 |
| Tool registry/toolsets | `workflows/registry.py`、`toolsets.py` | 只消费 Core 传入的 capability view |
| Skills | AstrBot Skill 只读 adapter 和本地 recipe 候选 | 可参与 proposal 检索，但不能执行 |
| Executor backend | Core capability executor；sidecar/container 只做 posture 或未来 runner | 无 executor |

## 拆分与合并对比

### 保留拆分的优势

- 信任边界清楚：Center 输出永远是不可信 draft，Core 必须重编译。
- 开发隔离：proposal、多模型、skill 检索可以频繁迭代，不污染 Core 执行面。
- 部署可裁剪：轻量用户只安装 Core；需要复杂 planning 的用户再启用 Center。
- 故障隔离：Center 挂掉不会破坏 Core 的记忆、Web、命令和手工 workflow。
- 模型成本可控：高成本 planner/coding/critic 角色集中在 Center 或 advisor layer。

### 保留拆分的成本

- 安装和配置多一个插件。
- 需要 token、URL、超时和健康检查。
- Core 与 Center 需要维护 proposal contract 版本，防止漂移。
- capability 元数据可能重复，必须以 Core 传入的 view 为准。

### 合并的优势

- 部署更简单。
- 无 HTTP 调用延迟和 token 配置。
- 调试时调用栈更短。
- 适合 Center 只剩本地 fallback proposer 的情况。

### 合并的风险

- proposal 试验容易滑入 Core 执行边界。
- 多模型顾问链和 skill 检索会继续把 Core 做大。
- 用户会误以为“规划通过”等于“允许执行”。
- 后续如果引入 sidecar/runner/marketplace，会再次拆分。

## 判定规则

保留拆分的条件：

- Center 使用独立 advisor model、专门 prompt、critic review 或更复杂 proposal 质量控制。
- Center 需要读取或索引 AstrBot Skill/recipe 目录。
- Center 需要 proposal 缓存、模板检索、版本化 contract 或专门 Web 管理页。
- Center 未来可能独立部署到更强模型或外部 planner 服务。

考虑回收合并的条件：

- 连续两个迭代中 Center 只做 `_fallback_draft` 或简单 prompt 包装。
- Center 无独立配置、无独立模型、无独立验证脚本价值。
- 用户部署复杂度明显高于 proposal 质量收益。
- Core 与 Center 的 contract 维护成本超过拆分收益。

若合并，目标不是把 Center 逻辑塞回 `main.py`，而是移动到：

```text
workflows/proposal/
  builder.py
  advisor_chain.py
  contract.py
  recipe_search.py
```

## 对话核心优化计划

当前 `main.py` 已经比早期薄，但仍直接承载消息摄入、LLM prompt 注入、response 记录、bridge 和命令分发。`dialogue/` 已作为顶层包落地，下一步方向是让它成为 Core 内部秘书中枢，而不是简单的 prompt 注入器。

建议新增：

```text
dialogue/
  models.py          # TurnContext, DialogueDecision, route/intent 类型
  analyzer.py        # Core-owned turn analyzer，输出受控分支
  router.py          # 兼容旧 router API，委托 analyzer
  context_policy.py  # 记忆检索、person_info、proactive、concept 的上下文预算策略
  observer.py        # response 后记忆、概念、情绪、recall gap 更新
  service.py         # 观察、自动派发、prompt 注入 facade
  dialogue_center.md # 模块边界文档
```

对话核心原则：

- 普通消息先由 analyzer 裁定为聊天、只读 workflow、待确认 workflow、skill 候选或拒绝。
- 自然语言 workflow 使用独立 surface：`dialogue_read`、`dialogue_pending`、`dialogue_skill`。
- 只读和 skill 候选结果注入本轮 prompt 继续聊天；待确认写入直接返回 pending workflow。
- Analyzer 输出本地枚举，不允许模型自由发明 route 名。
- Prompt policy 输出结构化 blocks，再由 `prompt/` 渲染预算。
- Response observer 只做记忆沉淀、概念、画像、recall gap 和 mood；写入仍走服务层。
- 只有命中 workflow 分支的 turn 写入 `workflow_runs`；普通聊天只保留消息/响应观察与 prompt context。

## Workflow Center 二期优化计划

目标是让 Center 更像 Hermes 的 toolset consumer，而不是自由生成器。

### Contract V3

Core 请求必须带：

- `contract_version`
- `intent`
- `turn_context`：scope、actor、source、is_wake、message_type、route_hint。
- `toolset`：profile、surface、capability_view_hash、hidden/disabled 摘要。
- `capabilities`：Core 裁剪后的 capability schema。
- `constraints`：max_steps、write_policy、risk_policy、allowed_outputs。
- `recipe_candidates`：来自 AstrBot Skill adapter 或本地 pack 的只读候选。

Center 返回必须带：

- `proposal`
- `advisor_trace`
- `critic_review`
- `local_scan`
- `uses_only_visible_capabilities`
- `proposal_hash`
- `capability_view_hash_echo`
- `contract_version`
- `center_metadata`

Core 仍只信任自己重新计算的 hash、risk 和 confirm policy。

### Center 内部结构

当前 `core/proposer.py` 仍接近 500 行上限。下一步拆分为：

```text
core/
  proposer.py        # facade
  contract.py        # request/response validation and versioning
  toolset.py         # capability filtering and metadata
  advisor_chain.py   # planner/coding/memory + critic staged chain
  fallback.py        # deterministic fallback draft
  policy.py          # local proposal-only scan and stable hash
```

拆分后 `main.py` 继续只负责 AstrBot 注册、HTTP API、token 校验和 provider 解析。

### Center 验证增强

- 新增只读校验脚本检查 Center 不注册 executor API。
- 检查 `proposal` 不包含未知 capability。
- 检查 contract version、hash echo、advisor trace 和 policy notes。
- 检查单文件不超过 500 行。

## 优先实施顺序

1. P45-01 固化本计划和拆分决策。
2. P45-02 新增 `dialogue/` 模块骨架，只迁移路由/上下文策略，不改业务行为。
3. P45-03 把 `main.py` 的 LLM request/response hook 委托给 dialogue service。
4. P45-04 定义 Workflow Center Contract V3，并让 Core client 发送 turn_context 与 contract_version。
5. P45-05 拆分 Workflow Center `core/proposer.py`。
6. P45-06 更新 Web/README/ARCHITECTURE/模块文档和验证脚本。

## 本轮推荐决策

采用“保留拆分 + 强化契约 + Core 独立可运行”的方案。

这比立即合并更适合当前积极开发阶段；同时用判定规则保留未来合并路线，避免为拆分而拆分。
