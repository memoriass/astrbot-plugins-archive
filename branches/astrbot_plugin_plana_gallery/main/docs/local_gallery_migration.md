# Local Gallery Migration

## 从远端 provider 版本升级

新版本不再加载 Lsky、Chevereto 或 Lychee provider，也不注册远端上传和同步接口。

升级不会删除：

- 本地图片文件。
- `gallery_assets` 和稳定 `asset_ref`。
- 标签、caption、审核和 tombstone。
- 旧 `gallery_remote_assets` 记录。

新版本会：

1. 创建 `gallery_schema_meta` 并写入 schema version 2。
2. 创建规范标签、别名、聊天候选事件和 FTS 表。
3. 旧资产的标题、caption、来源、路径和 JSON 自由标签保持原样；迁移只在派生标签索引中记录旧的已打标资产可作为兼容安全候选，不把系统标签写回旧 JSON 标签。

标签编辑与审核通过已拆分：保存自由标签不会自动移除 `needs-review`，管理员必须显式执行“确认通过”。
4. 重建 FTS 派生索引。
5. 停止所有 remote mapping 写入。

## 历史映射导出

如需归档旧远端 URL，可只读查询：

```sql
SELECT asset_id, provider, remote_key, remote_url, status, updated_at
FROM gallery_remote_assets
ORDER BY updated_at DESC;
```

不要把历史 URL 重新写回资产事实表。Core 只使用 `asset_ref` 和 Gallery resolve 返回的本地文件。

## 回滚

回滚旧插件前先备份整个 Gallery 数据目录。schema v2 只新增表并为已审核资产补充安全标签，没有删除旧 remote 表；旧版本通常可以继续读取资产，但不会理解新标签定义和候选事件。
