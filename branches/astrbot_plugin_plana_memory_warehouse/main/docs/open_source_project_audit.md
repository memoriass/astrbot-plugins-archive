# Memory Warehouse 开源项目代码审计

审计日期：2026-07-12

## 1. 当前仓库基线

- 仓库：`astrbot_plugin_plana_memory_warehouse`，版本 `0.1.0-beta.1`。
- Git 已补齐：当前分支 `main`，审计基线 commit `8f906003f5b49e332667edd8658981353b008f7f`（`first commit`）。
- 入口保持轻量；`plugin/runtime.py` 负责 AstrBot 生命周期和 loopback HTTP，存储职责已拆到 `store_schema.py`、`store_search.py`、`store_maintenance.py`。
- 持久化使用 SQLite WAL、`warehouse_events` 与 FTS5 索引；稳定 evidence id 支持按 `external_event_id` 幂等更新。
- API contract 为 `plana.memory_warehouse.v1`，支持 ingest、bulk ingest、search、recent、get、rebuild-index 和 prune。
- 2026-07-12 验证基线：`python -m compileall -q .`、`python scripts/check_memory_warehouse_plugin.py` 与 `git diff --check`。检查脚本会只读报告已跟踪的 `__pycache__`/`.pyc` 污染，不删除缓存或运行数据。

## 2. 发现清单

### P0

当前没有代码级 P0；发布前仍需清理已跟踪缓存并建立可复现 tag，但本轮只记录，不删除或提交。

### P1

1. **Git 发布卫生仍未闭环。** `.gitignore` 已覆盖 Python 缓存、SQLite、backup、restore candidate 与临时目录，但 baseline commit 已跟踪部分 `.pyc`；发布负责人需在联调结束后单独移出 Git 索引并确认不包含运行数据。
2. **备份恢复已完成第一阶段，仍缺停服切换演练。** 当前已提供在线 SQLite backup、manifest/hash/integrity 校验和独立恢复候选；仍需验证真实 AstrBot 停服、替换、重启与回滚流程。
2. **删除传播契约不完整。** prune 只按时间删除 evidence；尚无从 Core 发起的 tombstone、按 actor/scope/evidence 删除传播、删除审计和远端副本确认。
3. **检索质量缺少固定评测。** 当前 smoke test 覆盖英文 FTS、中文 LIKE、scope/actor 和幂等更新，但未覆盖事实更正、时间冲突、说话人误归因、过期偏好和跨群共享误召回。
4. **容量边界未证明。** 没有百万级 evidence、FTS rebuild 时间、WAL 增长、并发读写、prune 批次和磁盘占用基准。
5. **Core direct Store fallback 破坏插件边界。** Core 应只通过 loopback contract 调用 Warehouse；直接导入 Store 会让 schema 和运行时升级形成隐式耦合。

### P2

1. **没有显式时间有效性模型。** `created_at` 可以排序，但没有 valid-from/valid-to、supersedes、contradiction group 或 confidence history。
2. **没有可重建的语义/图候选层。** 当前不应立刻引入，但后续可以在固定评测证明关键词检索不足后加入可删除重建的 embedding/graph 索引。
3. **召回解释仍偏底层。** 建议返回裁剪原因、匹配字段、scope 决策和时间命中理由，供 Core ExplanationService 使用。

## 3. 开源候选矩阵

查询来源为 GitHub 官方仓库/API，状态记录于 2026-07-12。

| 项目 | 许可证/近期状态 | 可借鉴机制 | 依赖成本 | 裁决 |
| --- | --- | --- | --- | --- |
| `mem0ai/mem0` | Apache-2.0；2026-07-11 推送；release `ts-v3.0.13` | 记忆抽取、更新/删除、图记忆和评测思路 | 高，带 provider/vector store 抽象 | 仅借评测和冲突场景，不替换 Store |
| `letta-ai/letta` | Apache-2.0；2026-07-03 推送；release `0.16.8` | 分层上下文、可追踪 memory blocks、agent state | 高，完整 agent runtime | 借注入追踪与块级更正，拒绝 runtime |
| `getzep/graphiti` | Apache-2.0；2026-07-09 推送；release `v0.29.2` | 时序知识图、事实有效期、关系更新 | 中高，需要图数据库/模型 | 固定评测通过后再做可选实验 |
| Angel Memory / NachoBot（本地） | 本地参考仓库 | 关系连续性、激活、跨 scope 体验 | 不作为依赖 | 借评测样例，不复制数据层 |

官方来源：

- `https://github.com/mem0ai/mem0`
- `https://github.com/letta-ai/letta`
- `https://github.com/getzep/graphiti`

## 4. 深审结论

### 可直接借鉴

- 建立事实更正、过期、冲突、删除和跨 scope 的固定回归数据集。
- 为 Core 注入保存 evidence id、来源、scope、actor、时间和裁剪原因。
- 将附加索引设计为可丢弃、可重建，而 SQLite evidence 继续作为事实来源。

### 需适配借鉴

- Graphiti 的时间有效性可压缩为 SQLite `valid_from`、`valid_to`、`supersedes_id` 和 contradiction metadata，先不引入图数据库。
- Mem0 的 update/delete 语义应转换为 Core 决策后产生的明确 Warehouse tombstone，而不是 Warehouse 自行判断记忆价值。
- Letta 的 memory block 只用于设计 Core 注入追踪，不引入其 agent state/runtime。

### 禁止引入

- 让第三方 LLM 自动把 raw evidence 提升为长期画像。
- 由 Warehouse 直接写 Core profile/relation，或把不同用户/群聊默认合并。
- 在没有基准收益前增加常驻向量数据库、图数据库或云端记忆服务。

## 5. 目标架构与数据流

```text
Core evidence policy
  -> loopback ingest/search contract
  -> SQLite canonical evidence + FTS
  -> optional rebuildable semantic/temporal index
  -> bounded evidence + explanation metadata
  -> Core promotion/conflict/confirmation policy
```

Warehouse 只拥有 evidence、索引、保留期、备份与恢复；Core 继续拥有事实提升、画像、关系、prompt 注入和删除授权。

## 6. 实施任务

1. **建立发布基线**：初始化 Git、记录当前代码快照、创建首个 beta tag；完成标准是可从 tag 重建插件并通过现有 check。
2. **备份恢复闭环**：在线 backup、manifest 和 restore candidate 已实现；下一步增加停服切换、上一版本数据库恢复和损坏备份演练脚本。
3. **删除传播 V1**：定义 Core 发起的 evidence/scope/actor tombstone contract，保留删除审计并使索引同步移除。
4. **记忆质量 benchmark**：加入更正、过期、冲突、说话人、跨群和空结果数据集，输出 precision/recall 与错误类型。
5. **容量 benchmark**：覆盖 10 万和 100 万 evidence、FTS rebuild、prune、WAL 与并发查询。
6. **移除 direct fallback**：Core 只依赖 HTTP/client contract；开发环境使用统一 fixture，不导入 Warehouse Store。
7. **时间语义实验**：仅在 benchmark 证明需要后增加 additive metadata，不改变现有 v1 返回兼容性。

验证：现有 compile/check，加备份恢复、删除传播、迁移中断、容量和 contract fixture。所有写测试只使用临时目录。

## 7. 最终裁决

- **立即实施**：Git 基线、备份恢复、删除传播、固定评测、容量基准、移除 direct fallback。
- **验证后实施**：SQLite 内的时间有效性和 contradiction metadata。
- **暂缓**：embedding 与图索引。
- **拒绝**：替换为完整 Mem0/Letta runtime、云端自动记忆写入、Warehouse 自主提升画像。

## 8. 实施后复审（2026-07-12）

- 已完成 SQLite online backup、JSON manifest、SHA-256/integrity/FTS 校验和独立 restore candidate。
- 已完成显式 evidence/scope/actor 删除、dry-run、确认边界、request id 幂等和删除审计。
- Windows 文件句柄、路径逃逸、备份篡改、恢复候选不覆盖在线库和重复删除均已进入临时目录测试。
- 仍未完成：Git 基线、停服替换/回滚演练、百万级容量 benchmark、Core direct Store fallback 移除和时间冲突评测。

## 9. 合并裁决实施

- Warehouse 保持独立；Core 已移除 direct Store fallback，只允许 Contract V1 loopback HTTP。
- 新增临时目录质量/容量 benchmark，默认 1000 条 smoke；发布验证使用 `--events 100000`，扩展验证使用 `--events 1000000`。
- benchmark 覆盖更正事实样例、scope/actor 隔离、FTS rebuild、吞吐和数据库体积；不修改在线 Warehouse 数据。
