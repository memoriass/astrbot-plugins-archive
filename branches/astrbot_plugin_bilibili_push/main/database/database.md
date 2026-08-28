# database 模块

`database` 负责 SQLite 持久化长期业务数据。订阅、账号池、会话目标和 UP 别名都在 SQLite 中，不再使用 JSON 作为长期业务存储。

## 文件职责

- `db_manager.py`: 对外入口，组合订阅、账号、目标会话和别名存储能力，并统一创建 SQLite 连接。
- `schema.py`: 当前 SQLite 表结构定义，只描述新结构，不承载旧数据兼容迁移。
- `models.py`: 订阅和目标会话的轻量数据对象。
- `subscriptions.py`: 订阅增删改查，以及按 target 启用状态过滤调度数据。
- `accounts.py`: Bilibili 账号池持久化，包括 Cookie、启停状态、风控冷却和失败计数。
- `aliases.py`: UP 主简称、网络代称、确认历史映射和跨会话证据，用于减少 AI workflow 重复搜索和候选确认。
- `targets.py`: 群/会话目标索引，提供启停能力，后续分群策略从这里扩展。

## 当前表

- `subscriptions`: 用户订阅，主键为 `uid + sub_type + target_id`，`enabled` 控制是否参与调度。
- `accounts`: Bilibili 账号池，存登录 Cookie、启停状态、风控冷却和失败计数。
- `targets`: 会话/群目标索引，存 `target_id`、渠道和启停状态；订阅写入时会自动登记。
- `up_aliases`: UP 主别名和历史确认映射，主键为 `normalized_alias + uid + target_id`，支持当前会话优先和全局用户名兜底。
- `up_alias_evidence`: 跨会话别名证据，主键同样为 `normalized_alias + uid + target_id`。它记录每个会话确认过的简称，不直接作为全局别名；实体解析时会聚合不同会话数量，只有多会话一致且无竞争 UID 时才自动推进。

## SQLite 策略

- 所有模块通过 `DatabaseManager._connect()` 创建连接，不直接调用 `sqlite3.connect()`。
- 连接启用 `PRAGMA journal_mode = WAL`，用于降低 WebUI、调度器和 workflow 并发读写时的互相阻塞。
- 连接设置 `PRAGMA synchronous = NORMAL`，在 WAL 模式下兼顾性能和持久化安全。
- 连接设置 `PRAGMA busy_timeout = 5000`，遇到短暂锁等待时最多等待 5 秒。
- 连接设置 `PRAGMA foreign_keys = ON`，为后续增加外键约束预留一致行为。

## KV 边界

以下状态仍保留在 AstrBot KV，不迁入 SQLite：

- `bili_workflow_pending_tasks`: AI workflow 待处理任务。
- `seen_posts_{uid}`: 动态去重窗口。
- `live_status_{uid}`: 直播状态缓存。
- `search_cache_{keyword}`: UP 搜索缓存。
- `bili_avatar_cache`: UP 头像 URL 缓存。订阅和管理页展示会复用该缓存；长时间未被订阅或使用的条目会在后续访问时清理。

这些数据是短期状态或缓存，适合 KV；订阅、账号、会话目标和别名是长期业务数据，必须走 SQLite。

## 文件缓存边界

- `plugin_data/astrbot_plugin_bilibili_push/image_cache/avatars/`: 聊天卡片渲染用的头像图片本体缓存。缓存键包含头像 URL 和压缩策略，图片 24 小时过期，120 天未使用会自动清理。

## 维护说明

- `add_subscription()` 使用普通 `INSERT`，重复订阅返回 `False`，不要改回覆盖写入。
- `get_subscriptions()` 返回全部订阅；调度器应使用 `get_enabled_subscriptions()`，它会同时过滤已停用订阅和已停用 target。
- `set_subscription_enabled()` 只更新启停状态，不修改分类、标签和用户名。
- WebUI 和 workflow 写操作必须提供完整定位字段，避免跨会话误改。
- 新增字段需要同步 `schema.py`、序列化、WebUI 表单和校验脚本。
- 新增表或字段后，同步更新 `webapi/manager_serializers.py`、`pages/manager/` 表单字段和 `scripts/check_workflow_integration.py` 的覆盖范围。
- `up_aliases` 解决当前会话和官方用户名的快速命中，`up_alias_evidence` 解决多群共享证据；不要把用户昵称类简称直接写成无条件全局别名。
- 共享别名证据允许跨群增强命中率，但一旦同一简称指向多个 UID，解析层必须降级到搜索或候选卡，不能自动写库。
- UP 解析统计是运行态诊断数据，保存在插件内存中，不写入 SQLite；不要为短期命中率统计新增持久表。
