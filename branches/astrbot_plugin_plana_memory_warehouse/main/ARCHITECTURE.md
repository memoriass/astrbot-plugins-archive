# Plana Memory Warehouse 开发架构

Plana Memory Warehouse 是 Plana 插件族的长期情景证据仓库。它把 raw episodic evidence、stable evidence ID、检索索引和后续备份恢复能力从 Core 拆出，避免 Core 变成无限聊天日志库。

Warehouse 不拥有 Core prompt policy、画像/关系 mutation、workflow execution、外部发送或 proactive delivery。

## 模块边界

- `main.py`: 薄入口，只 re-export AstrBot plugin class。
- `plugin/runtime.py`: AstrBot plugin 生命周期、可选兼容采集、命令、HTTP API 和本机回环校验。
- `plugin/capture.py`: 可选兼容采集器；默认关闭。推荐由 Core 生成 warehouse evidence payload。
- `plugin/config.py`: 配置归一化、数值边界和 prune 窗口解析。
- `plugin/store.py`: SQLite warehouse 主类、幂等 evidence 写入、批量导入、row 序列化和连接边界。
- `plugin/store_schema.py`: SQLite schema、additive migration 和索引定义。
- `plugin/store_search.py`: FTS5/LIKE 混合检索和 recent 过滤。
- `plugin/store_maintenance.py`: FTS 重建、保留期清理和状态摘要。
- `plugin/maintenance_api.py`: maintenance HTTP handlers；备份、校验和恢复候选均保持 loopback 与确认边界。
- `plugin/store_common.py`: contract 常量和通用清洗 helper。
- `_conf_schema.json`: Core 调用入口、采集开关、内容长度、批量导入、检索限制、保留期和调试命令开关。
- `scripts/check_memory_warehouse_plugin.py`: 本地结构和 store smoke check。

## Human-Like Memory Split

- Core `dialogue/ledger.py`: 短期工作记忆，进程内保存。
- Memory Warehouse: 长期原始情景 archive、evidence、附件元数据和大索引。
- Core memory/profile/relation: 语义投影、画像、关系、召回策略、确认和审计。

Core 可以按 evidence ID hydrate 证据片段，但 prompt 注入、事实写入、删除、冻结、恢复和关系更新仍由 Core 决定。

## API Contract

- `GET /plana_warehouse/state`: 仓库状态。
- `POST /plana_warehouse/evidence/ingest`: 写入一条 evidence event。
- `POST /plana_warehouse/evidence/bulk-ingest`: 批量导入 evidence events。
- `GET|POST /plana_warehouse/evidence/search`: 按 query/scope/scope_ids/shared_scope_ids/origin/actor 检索。
- `GET|POST /plana_warehouse/evidence/recent`: 查看最近 evidence，可按 scope/origin/actor/role/event_type 过滤。
- `GET /plana_warehouse/evidence/get?evidence_id=...`: 读取 evidence 详情。
- `POST /plana_warehouse/maintenance/rebuild-index`: 重建 FTS 索引，必须带 `confirm=true`。
- `POST /plana_warehouse/maintenance/prune`: 清理过期 evidence；执行删除时必须带 `confirm=true`。
- `POST /plana_warehouse/maintenance/backup`: 使用 SQLite online backup 创建一致性备份；必须带 contract version 与 `confirm=true`。
- `POST /plana_warehouse/maintenance/backup/validate`: 只读校验备份 hash、manifest、SQLite integrity 和 FTS 行数。
- `POST /plana_warehouse/maintenance/restore-candidate`: 将已验证备份复制为独立恢复候选；必须确认，且不会替换在线数据库。
- `POST /plana_warehouse/maintenance/delete-evidence`: 按 evidence、scope 或 actor 预览/确认删除；确认请求使用稳定 request id 幂等，并写入不含正文的删除审计。

请求 contract version 为 `plana.memory_warehouse.v1`。默认同机安装时，Core 访问 `http://127.0.0.1:6185/api/plug/plana_warehouse`，Warehouse 只接受无代理转发头的本机回环请求。跨主机、反代或公网入口不支持零散 token/header 配置，需要跨边界时应通过 Bridge Gateway 或专用网关重新设计。

默认模式是被动仓库：Core 负责采集、裁剪、脱敏、structured memory extract、profile snapshot、daily maintenance summary 和是否推送；Warehouse 只接收 evidence 并维护索引。`capture_messages`、`capture_llm_responses` 和 `allow_commands` 默认关闭。确需兼容独立采集时再开启，并用 `excluded_prefixes` 排除敏感前缀。

调试命令开启后，`search` 和 `recent` 必须绑定当前会话 `unified_msg_origin`；无法解析 origin 时直接跳过，不能全局检索 raw evidence。

### Cross-Scope Actor Recall

Warehouse search accepts a primary `scope_id`, optional `scope_ids`, optional `shared_scope_ids`, and `actor_id`. This mirrors the NachoBot/A_memorix style: Core can look at the current chat, approved shared chats, and the same actor's long-term archive without duplicating person memories per group.

This is still evidence replay, not memory promotion. Warehouse returns bounded snippets and evidence IDs only. Core decides whether a stable fact becomes global profile data, whether a group-local fact remains scoped, and whether any write needs confirmation.

## Storage

数据保存在 AstrBot 插件数据目录下的 `memory_warehouse.sqlite3`。

备份保存在同一插件数据目录的 `backups/`，包含 SQLite 文件与相邻 JSON manifest。恢复准备只写入 `restore_candidates/`；运行时没有“直接覆盖在线数据库”接口，正式切换必须停服后由维护者核对路径、hash 和版本再执行。

备份保存在同一插件数据目录的 `backups/`，包含 SQLite 文件与相邻 JSON manifest。恢复准备只写入 `restore_candidates/`；运行时没有“直接覆盖在线数据库”接口，正式切换必须停服后由维护者核对路径、hash 和版本再执行。

- `warehouse_events`: canonical evidence rows。
- `warehouse_events_fts`: evidence content FTS5 index。
- `warehouse_deletion_audit`: 删除 request id、selector、命中数与删除数，不保存被删正文。

Search 返回 bounded snippet 和 coverage metadata。未命中或仓库不可用不能被 Core 解读为事实不存在。

Core 的结构化抽取、画像快照和每日维护摘要都使用 Core-owned metadata 标记。每日维护摘要使用稳定 external event ID，同一天多次维护会更新同一条 evidence，模拟海马体式短期沉淀到长期证据仓库。

Evidence ID 规则：

- 如果 payload 提供合法 `evidence_id`，导入时沿用。
- 如果有 `external_event_id`，按 scope/origin/external_event_id 生成稳定 ID，重复导入会更新同一行。
- 否则按 scope/origin/actor/role/event_type/created_at/content_hash 生成 ID，适合原始消息流采集。

## 维护规则

- 新字段必须保持 additive migration，不破坏现有 evidence ID。
- status 不暴露本机绝对数据库路径。
- API 返回内容必须有长度上限。
- Warehouse 不直接写 Core 表，不触发 Core workflow。
- 批量维护操作必须先 dry-run 或显式确认；命令和 API 都不能静默删除或重建。

## 验证

```powershell
python -m compileall -q .
python scripts\check_memory_warehouse_plugin.py
git diff --check
```
