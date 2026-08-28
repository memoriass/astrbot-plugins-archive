# astrbot_plugin_ani_rss

AstrBot 的 ANI-RSS 订阅助手插件。

插件提供 `ani_rss` Agent 工具，用于通过自然语言搜索 Mikan、选择番剧和字幕组，并把 RSS 订阅提交到 ANI-RSS。

## 主要能力

- 自然语言添加番剧订阅。
- 自然语言会先按上下文和置信度分流到受控 workflow。
- 搜索 Mikan 番剧和字幕组 RSS。
- 推荐本季或指定条件的 Mikan 候选。
- 选定 Mikan 字幕组后自动添加到 ANI-RSS。
- 写入前检查已启用订阅，避免重复添加同一 RSS 或同一 Bangumi/字幕组。
- 学习当前会话常用字幕组和语言偏好，默认把常用项排前。
- 记录 workflow 工具结果，并让字幕组偏好吸收负反馈与近因衰减。
- RSS 直连添加会先生成确认卡片。
- 支持查看已启用订阅、刷新单个订阅、刷新全部订阅。
- 已启用订阅列表默认展示前 20 条，并按 ANI-RSS 星期分组。
- 默认使用图片卡片展示候选和结果。

## 配置项

- `base_url`: ANI-RSS 服务地址。
- `api_prefix`: ANI-RSS API 前缀，通常为 `/api`。
- `api_key`: ANI-RSS API Key。
- `timeout_seconds`: API 请求超时。
- `interaction_timeout_seconds`: 用户选择/确认等待时间。
- `pending_task_ttl_seconds`: 挂起任务保留时间。
- `subscription_cache_ttl_seconds`: 订阅列表缓存时间，添加成功后会自动失效。
- `mikan_search_cache_ttl_seconds`: Mikan 搜索、番剧详情和字幕组缓存时间。
- `preference_mode`: 偏好学习模式，`off` / `rank` / `auto`。
- `preference_min_uses`: `auto` 模式允许自动选择前的最少使用次数。
- `storage_cleanup_interval_seconds`: 过期挂起任务和缓存的清理间隔。
- `render_mode`: 卡片发送模式，支持 `image` / `text` / `both`。

运行数据存储在 AstrBot 数据目录：`data/plugin_data/astrbot_plugin_ani_rss/state.sqlite3`。

Ubuntu 22.04/24.04 等较新的 Linux 环境可正常安装图片渲染依赖；渲染器不可用时，`image` / `both` 会自动回退为文本，不影响订阅流程。

## 使用方式

优先使用自然语言：

```text
推荐几部本季新番
帮我订阅淡岛百景
查一下淡岛百景有没有字幕组
查看 ANI-RSS 已启用订阅列表
刷新全部订阅
```

候选卡片会带任务 ID。继续挂起任务时使用：

```text
/ani<任务ID前后几位> <序号|确认|取消>
```

命令前缀来自 AstrBot 全局 `wake_prefix`。例如唤醒词是 `plana` 时：

```text
plana ani<任务ID前后几位> <序号|确认|取消>
```

## 维护文档

根目录只保留 `main.py` 作为插件入口，其余 Python 代码按职责放在模块目录下。

- `PROJECT_OVERVIEW.md`: 项目大纲。
- `plugin/PLUGIN_RUNTIME.md`: 插件运行时结构。
- `COMMAND_ROUTING.md`: 命令和短任务 ID 路由。
- `integrations/ANI_RSS_API.md`: ANI-RSS API 访问层。
- `workflows/WORKFLOW_ARCHITECTURE.md`: 工作流编排。
- `ui/CARD_RENDERING.md`: 卡片渲染。
- `scripts/COMPATIBILITY_LAYER.md`: 兼容层。
