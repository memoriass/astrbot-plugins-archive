# LivingMemory 兼容与借鉴审查

## 结论

LivingMemory 可以作为 Plana 记忆系统的算法参考，但不适合作为整套运行时直接接管 Plana Core。Plana 是 AstrBot 框架内的秘书中枢，长期记忆、workflow、Web、审计和确认边界已经由 Core 统一编排；直接移植 LivingMemory 的 graph/vector/index runtime 会形成第二套记忆系统，增加维护成本和权限边界复杂度。

当前采用的路线是：复用思想，Plana-native 落地，并提供 LivingMemory 常用功能的兼容入口，做到不引入但可平替。

## 2026-07-13 生产迁移

- 201 已停止加载 LivingMemory 插件；源码、配置和原数据库移入 `retired_*` 目录，不再参与 AstrBot hook 和 prompt 注入。
- `scripts/migrate_livingmemory_to_core.py` 从 LivingMemory 活动 atom 中迁移稳定事实，按内容去重并记录 `livingmemory_migration_map`，可安全重复执行。
- 本次源库包含 41 条活动 atom：31 条迁入 Core，10 条机器人自述和机械流程话术被过滤。
- 迁移结果包含 31 条 episodic memory、31 条 Core atom；其中与零相关的 12 条用户事实投影为全局 profile semantic，并同时映射 `aiocqhttp:924781982` 与生产 ChatUI 的 `webchat:root`。
- 真实 ChatUI 验证“我之前说 token 主要拿去做什么了”能够由 Core 独立回答“主要拿去写插件”，不依赖 LivingMemory 运行时。

## 已落地

- 记忆原子评分：参考 LivingMemory atom retrieval 的时间衰减与综合评分思路，在 `memory/atom_policy.py` 增加 `temporal_score` 与 `final_score`。
- Atom 检索排序：`memory/atoms.py` 对 FTS/LIKE 候选去重后按综合分、重要度、创建时间排序。
- 召回可解释性：`memory/recall.py` 的 atom route metadata 暴露 TTL、decay type、reinforcement count、temporal score 和 final score。
- Web 记忆详情：`web/inspectors.py` 与 `web/page.py` 在记忆详情中展示 memory atom 切片，方便用户判断召回来源。
- Recall gap 闭环：`memory/recall_gap_service.py` 将未命中问题转为 pending memory feedback，只有确认处理后才写入长期记忆并标记 gap resolved。
- Workflow 接入：`memory.recall_gap_propose` 作为 medium risk、本地写入、需要确认的能力注册，避免自然语言直接写记忆。
- 命令兼容：`/lmem status/search/forget/rebuild-index/rebuild-graph/webui/summarize/reset/cleanup/help` 由 `plugin/livingmemory_compat.py` 映射到 Plana 的记忆、维护、图谱和 Web 服务。

## 暂不移植

- 不移植完整 Graph2D 前端。Plana Web 已有概念图和记忆详情面板，后续只吸收布局、分页、聚类和大数据量降采样策略。
- 不移植完整 vector/index rebuild runtime。Plana 继续使用 SQLite、FTS、可选 embedding 与现有维护脚本，避免形成两个索引生命周期。
- 不移植独立插件入口和全局调度。Plana 的入口仍在 `MemoryKernel`、Web API、workflow capability 和后台 job 内。

## 后续可继续吸收

- Canvas 大数据量策略：按 scope、类型、重要度和时间窗口分页加载，前端只渲染可见节点。
- 遗忘机制 UI：把 active、expired、forgotten、reinforced 状态做成可筛选视图，并显示为什么被衰减或保留。
- Recall gap 运营页：在 Web 上展示 open/candidate/resolved 三类缺口，允许用户把 open gap 转为候选记忆。
- 反馈闭环指标：统计“未命中 -> 候选 -> 确认写入 -> 后续命中”的转化率，用于判断记忆系统是否真的改善。

## 平替口径

| LivingMemory 能力 | Plana 平替方式 |
| --- | --- |
| `/lmem status` | Plana 记忆统计、atom 状态、recall gap 和维护状态 |
| `/lmem search` | `MemoryKernel.search()` 的融合召回 |
| `/lmem forget` | Plana 审计删除，要求 `confirm` 确认边界 |
| `/lmem rebuild-index` | `MemoryMaintenance.backup()` + `rebuild_indexes()` |
| `/lmem rebuild-graph` | Plana 概念累计器，不复制 LivingMemory 图谱运行时 |
| `/lmem webui` | AstrBot 嵌入面板 `/api/plug/plana/dashboard` |
| `/lmem summarize` | Plana consolidation，将已记录消息沉淀为长期语义 |
| `/lmem reset` | 清理当前 scope/user 的 prompt 记忆冷却状态 |
| `/lmem cleanup` | Plana 不持久写入注入块；`exec` 映射为孤儿数据清理 |

这套平替面向功能与用户入口，不保证数据库、ID 命名、Web API 路径与 LivingMemory 完全一致；生产替换时应把用户操作说明迁移到 Plana 命令与 Web 面板。
