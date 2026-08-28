# database 模块

`database` 负责 SQLite 持久化长期业务数据。

## 文件职责

- `db_manager.py`: 对外入口，组合订阅、账号和目标会话存储能力。
- `schema.py`: 当前 SQLite 表结构定义，只描述新结构，不承载旧数据兼容迁移。
- `models.py`: 订阅和目标会话的轻量数据对象。
- `subscriptions.py`: 订阅增删改查，以及按 target 启用状态过滤调度数据。
- `accounts.py`: Bilibili 账号池持久化，包括 Cookie、启停状态、风控冷却和失败计数。
- `targets.py`: 群/会话目标索引，提供启停能力，后续分群策略从这里扩展。

## 当前表

- `subscriptions`: 用户订阅，主键为 `uid + sub_type + target_id`，`enabled` 控制是否参与调度。
- `accounts`: Bilibili 账号池，存登录 Cookie、启停状态、风控冷却和失败计数。
- `targets`: 会话/群目标索引，存 `target_id`、渠道和启停状态；订阅写入时会自动登记。

## KV 边界

以下状态仍保留在 AstrBot KV，不迁入 SQLite：

- `bili_workflow_pending_tasks`: AI workflow 待处理任务。
- `seen_posts_{uid}`: 动态去重窗口。
- `live_status_{uid}`: 直播状态缓存。
- `search_cache_{keyword}`: UP 搜索缓存。

## 维护说明

- `add_subscription()` 使用普通 `INSERT`，重复订阅返回 `False`，不要改回覆盖写入。
- `get_subscriptions()` 返回全部订阅；调度器应使用 `get_enabled_subscriptions()`，它会同时过滤已停用订阅和已停用 target。
- `set_subscription_enabled()` 只更新启停状态，不修改分类、标签和用户名。
- 如果新增字段，需要同步 `schema.py`、序列化、WebUI 表单和校验脚本。
- SQLite 方法保持同步调用即可，调用频率较低；不要在这里引入 AstrBot 依赖。
- WebUI 和 workflow 写操作必须提供完整定位字段，避免跨会话误改。
- 账号属于长期业务数据，必须通过 `accounts` 表读写；不要再保存到 AstrBot KV。
- `targets` 当前作为分群管理基础表，后续新增群别名、默认通知策略或账号绑定时优先扩展这里。
- 新增表或字段后，同步更新 `webapi/manager_serializers.py`、`pages/manager/` 表单字段和 `scripts/check_workflow_integration.py` 的覆盖范围。
