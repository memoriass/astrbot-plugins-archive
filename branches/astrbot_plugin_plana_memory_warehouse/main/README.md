# Plana Memory Warehouse

Plana Memory Warehouse 是 Plana 插件族的可选长期情景记忆仓库。它保存全量原始事件、证据 ID、检索索引和后续备份恢复边界；Plana Core 继续负责工作记忆、关系/概念图谱、用户画像、召回策略、prompt 预算、确认和审计。

推荐部署方式是由 Plana Core 统一筛选、裁剪和脱敏后推送 evidence。Warehouse 默认不自行监听 AstrBot 消息或 LLM 回复，只负责接收、存储、索引和检索。Core 可以推送 raw message、LLM response、structured memory extract、profile snapshot 和 daily maintenance summary 等 event_type；Warehouse 不把这些内容自行提升为画像或关系事实。

## API

- `GET /plana_warehouse/state`
- `POST /plana_warehouse/evidence/ingest`
- `POST /plana_warehouse/evidence/bulk-ingest`
- `GET|POST /plana_warehouse/evidence/search`
- `GET|POST /plana_warehouse/evidence/recent`
- `GET /plana_warehouse/evidence/get?evidence_id=...`
- `POST /plana_warehouse/maintenance/rebuild-index`（必须带 `confirm=true`）
- `POST /plana_warehouse/maintenance/prune`
- `POST /plana_warehouse/maintenance/backup`（必须带 contract version 与 `confirm=true`）
- `POST /plana_warehouse/maintenance/backup/validate`
- `POST /plana_warehouse/maintenance/restore-candidate`（必须确认，只生成独立候选）

在线备份使用 SQLite backup API，输出数据库文件和 JSON manifest；校验会检查 SHA-256、文件大小、SQLite integrity 和 FTS 一致性。恢复候选写入插件数据目录的 `restore_candidates/`，不会替换正在使用的数据库。

写入 payload 示例：

```json
{
  "contract_version": "plana.memory_warehouse.v1",
  "scope_id": "scope",
  "unified_msg_origin": "platform:group:123",
  "actor_id": "user-id",
  "role": "user",
  "event_type": "message",
  "content": "message text",
  "metadata": {}
}
```

批量导入 payload 示例：

```json
{
  "contract_version": "plana.memory_warehouse.v1",
  "items": [
    {
      "scope_id": "scope",
      "unified_msg_origin": "platform:group:123",
      "actor_id": "user-id",
      "role": "user",
      "event_type": "message",
      "content": "message text",
      "external_event_id": "platform:group:123:message-id"
    }
  ]
}
```

默认同机安装时，Plana Core 会访问 `http://127.0.0.1:6185/api/plug/plana_warehouse`；Warehouse 只放行无代理转发头的本机回环请求。跨主机、反代或公网入口不支持零散 token/header 配置，需要跨边界时应通过 Bridge Gateway 或专用网关重新设计。

检索 payload 可以按单个 `scope_id`、多个 `scope_ids`、额外 `shared_scope_ids` 和 `actor_id` 组合过滤：

```json
{
  "contract_version": "plana.memory_warehouse.v1",
  "query": "project preference",
  "scope_id": "group-a",
  "shared_scope_ids": ["global", "group-b"],
  "actor_id": "platform:user-id",
  "limit": 10
}
```

这个能力用于 Core 做跨群对象证据回放：同一对象在多个群出现时，Core 可以查当前群、共享群和该对象的长期 evidence，避免每个群重新积累一份重复画像。Warehouse 只返回 evidence/snippet，不负责判定这些片段是否进入 Core 画像。

Core 的普通聊天 `read_direct` 入口可以附加 Warehouse snippet，但仍是只读 evidence。默认只查当前 scope；显式跨群/仓库查询只应在私聊中按当前 `actor_id` 回放跨 scope evidence，群聊不直接暴露其他群片段。

## 命令

```text
/plana_warehouse_status
/plana_warehouse_search <关键词>
/plana_warehouse_recent [limit]
/plana_warehouse_rebuild_index confirm
/plana_warehouse_prune <days> [confirm]
```

`plana_warehouse_rebuild_index` 必须追加 `confirm`；`plana_warehouse_prune` 默认只预览命中数量，只有追加 `confirm` 才会删除数据。

## 关键配置

- `capture_messages`: 自动采集用户消息；默认关闭，推荐由 Core 推送。
- `capture_llm_responses`: 自动采集模型回复；默认关闭，推荐由 Core 推送。
- `capture_commands`: 是否采集 `/` 开头的命令；默认关闭，避免把 token、管理命令或调试内容写入仓库。
- `allow_commands`: 是否启用本插件调试命令；默认关闭。开启后 search/recent 只查询当前会话 origin，无法解析 origin 时直接跳过。
- `excluded_prefixes`: 逗号分隔的额外排除前缀。
- `max_bulk_items`: 单次批量导入上限。
- `retention_days`: 保留天数；0 表示不自动清理。
- `maintenance_on_start`: 启动时重建索引；如果设置了 `retention_days`，同时清理过期 evidence。

## 边界

- Warehouse 可以保存 Core 推送的原始 evidence、结构化 evidence、画像快照、每日维护摘要和大索引。
- Core 只通过 evidence ID 和 bounded snippet 使用 Warehouse。
- Warehouse 不执行 workflow，不直接修改 Core 画像、关系图谱或长期事实。
- Warehouse 不注册面向普通聊天的永久记忆写入工具；长期事实写入必须回到 Core。
- 写入长期事实、删除、冻结、保护、关系更新仍由 Core 的策略和确认边界决定。

开发边界见 `ARCHITECTURE.md`。
