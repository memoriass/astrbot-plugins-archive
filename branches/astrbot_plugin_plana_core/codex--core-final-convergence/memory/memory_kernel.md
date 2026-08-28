# Memory Kernel

`memory/` 维护 Plana Core 的长期记忆、召回、用户理解、反馈闭环和记忆治理。对话、Web、领域路由和后台维护应优先通过 `runtime.memory_kernel` 访问记忆能力。

## 文件职责

- `kernel.py`: search、ingest、profile、prompt context、recall gap、feedback 和 maintenance 的统一门面。
- `models.py`: memory kind 常量和 dataclass。
- `storage.py`: episodic/semantic/tool memory、link、decay event 和删除审计入口。
- `search_index.py`: episodic memory FTS5 索引，失败时回退 LIKE。
- `recall.py`: memory、semantic、concept、embedding 的 RRF 融合召回。
- `query_planner.py`: LLM 检索 query 规划。
- `classifier.py`: LLM 结构化记忆抽取。
- `quality.py`: LivingMemory 式 `canonical_summary` / `persona_summary` / `summary_quality` 评估；低质量总结只能留作 evidence，不提升为稳定画像。
- `recall_gap.py` / `recall_gap_service.py`: 未命中问题到 pending feedback 的闭环。
- `feedback.py`: useful、not_useful、new_memory、merge 反馈队列。
- `graph.py` / `graph_storage.py`: 概念图和扩散激活。
- `atoms.py` / `atom_policy.py`: memory atom 生命周期和策略。
- `maintenance.py`: SQLite 校验、备份、索引重建和孤儿清理。
- `scope.py`: scope alias 和跨 scope 迁移。
- `embedding.py`: 可选 embedding 存储和 provider 包装。
- `warehouse_client.py`: Memory Warehouse 推送和检索客户端。
- `warehouse_push.py`: Core-owned warehouse evidence 推送策略。
- `tokenizer.py`: 中英文搜索 term 提取。

## 数据流

1. 消息或显式请求写入 typed episodic memory。
2. LLM 回复后可抽取结构化记忆；每条结构化记忆带事实检索用 `canonical_summary`、人格注入用 `persona_summary` 和 `summary_quality`。
3. 只有 `summary_quality=normal` 的结构化记忆才能写入 semantic/profile/relation 投影；低质量或泛化总结仍可保存为事件和 Warehouse evidence。
4. Prompt 前由 query planner 和 `MemoryKernel.prompt_context()` 生成受预算限制的上下文。
5. Recall miss 写入 `recall_gaps`，只能转成 pending feedback。
6. 反馈处理和长期写入必须经过确认边界。
7. 后台维护执行 `global` 加最近活跃 scope 的 consolidate、decay、atom expiry 和 cleanup；concept accumulate 仍只在 `global` 执行。最近维护时间、Warehouse 推送数和错误原因必须进入 runtime/Dashboard 状态。

## ChatUI 回忆路径

- 明确的“调用记忆、搜索记忆、还记得”等请求走 AstrBot 原生 Tool Loop，只向该请求开放 `plana_recall_memory`。
- 主模型必须先调用真实召回工具，再把 evidence 总结成自然回复；不得生成执行提案或确认单，也不得向普通用户暴露内部 memory ID。
- 没有足够 evidence 时明确说明缺失范围。记忆未命中不等于知识库、外部服务或权限不存在。
- AstrBot Knowledge Base 继续负责静态文档 RAG；2026-07-14 生产 ChatUI 已用“基础插件指南”验证文档检索与回答链路。

## Memory Warehouse 边界

`astrbot_plugin_plana_memory_warehouse` 保存 Core 推送的长期原始 evidence、结构化 evidence、画像快照、每日维护摘要、附件元数据和大索引。Core 负责采集策略、裁剪、脱敏和是否推送；Warehouse 不自行决定记忆价值。

- Core 默认启用 Warehouse 客户端并指向 `http://127.0.0.1:6185/api/plug/plana_warehouse`；同机安装时先走 HTTP，若 AstrBot Dashboard 外层拦截 `/api/plug`，则在默认本机 URL 时回退到本地 Warehouse Store；跨主机或反代访问不支持零散 token/header 配置，应通过 Bridge/专用网关重新设计。
- Core 会在消息/回复通过本地记录策略后推送 evidence。
- Core 可把结构化抽取结果和画像快照推送给 Warehouse，用于审计、回放和后续离线整合；这些内容仍是 Core 生成的 evidence，不是 Warehouse 自行判定的事实。
- 结构化 evidence 会携带 `canonical_summary`、`persona_summary`、`summary_quality` 和 `promotable_to_profile`；Warehouse 只保存这些字段，不据此自行写回 Core。
- 自动维护会按 scope 写入每日幂等 summary，作为海马体式短期沉淀到长期仓库的索引点。
- 网络失败返回 `coverage_status=warehouse_unavailable`，不能当作事实不存在。
- snippet 只能作为召回证据，不能直接提升为画像、关系或长期事实。
- 写入、删除、冻结、恢复、画像刷新和关系更新仍由 Core 确认与审计。

### 跨群对象记忆

Plana 的跨群复用以 `actor_id` / `user_id` 为主轴，而不是把人物画像绑定到单个群。Core 写入当前 `scope_id` 的同时，只把偏好、昵称和明确稳定身份字段投影到 `global` profile；普通 `user_fact`、群内承诺、一次性任务、上下文笑话和局部关系仍留在当前 scope。

Prompt 激活默认仍检索当前 scope 的事件记忆和关系边；只有 Core 已投影到 `global` profile 的用户画像语义会按 `global_user_id` 合并回当前 prompt，并继续受 `memory_inject_max_chars` 和 `max_active_semantics` 限制。旧版无 scope 的关系边迁移为 `global`，不会自动进入普通群 scope prompt。

Warehouse 检索支持 `scope_id`、`scope_ids`、`shared_scope_ids` 和 `actor_id` 组合。Core 可以先查当前群 scope，再附加共享 scope 或 actor 全局 evidence；返回结果仍是 archive snippet，必须经过 Core 策略后才能进入 prompt、画像或关系写入。

## 维护规则

- 新 memory kind 必须加入 `ALL_MEMORY_KINDS`，同步 Web、README、架构文档和验证脚本。
- 新结构化抽取字段必须同步 `memory/quality.py`、Warehouse metadata、Dashboard/检查脚本；低质量总结不得绕过 `promotable` 边界写入画像。
- 数据表变更必须同步 `MemoryMaintenance._EXPECTED_TABLES`、维护 fixture 和代码验收矩阵。
- 删除、清理、迁移必须保留确认边界，并写入 audit。
- embedding 只能增强候选排序，不得绕过本地 ranking 和写操作校验。
- AstrBot 原生知识库通过 memory/knowledge_adapter.py 按需读取，只承载文档、API、Skill 和工作流说明。用户事实、任务连续性、资源权限与关系状态仍以 Core 为权威来源。
- semantic_memories 保持当前事实兼容接口；同值写入记录为 reinforced，值变化记录旧值 superseded 和新值 activated，历史保存在 semantic_memory_history。
- 文档检索结果是只读、不可信参考材料，不能携带执行指令、授权结论或凭据。普通个人记忆问句不会触发 AstrBot KB。
- unified_recall.py 将 Core recall、Warehouse evidence 和 AstrBot KB 规范化为统一候选，使用相关性、来源权威度、置信度和时效评分，并在最终候选上进行跨来源去重。
- Core Memory 候选参与统一排序但仍由现有 PromptBuilder 展示；统一补充块只输出 Warehouse 与 AstrBot KB，避免同一用户事实被重复注入。
- 普通聊天不会主动访问 Warehouse；只有“之前、上次、记得、说过、历史”等明确归档意图才允许查询。Warehouse 命中仍是 evidence，不会直接提升为画像。
