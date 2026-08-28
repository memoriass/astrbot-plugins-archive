# astrbot_plugin_ani_rss

AstrBot 的 ANI-RSS 订阅助手插件。插件提供 `ani_rss` Agent 工具，让用户用自然语言搜索 Mikan、选择字幕组，并把 RSS 订阅提交到 ANI-RSS。

当前版本：`1.1.3`

## 能力

- 自然语言添加番剧订阅，例如“帮我订阅躲在超市后门抽烟的两人”。
- 自然语言和不完整 Agent 工具参数会先进入 `ai_dispatch`，按上下文和置信度分流到受控 workflow。
- AI tool 调用交互型候选流程时默认只返回文本摘要和 task_id 给模型，不主动生成用户卡片；需要前台卡片可传 `interactive=true`。
- 支持 Mikan 搜索、季度推荐、番剧候选选择、字幕组选择。
- Mikan 搜索、番剧详情和字幕组列表使用短期缓存，降低重复查询延迟。
- 会学习当前会话常用字幕组和语言偏好，默认把常用项排前；可配置为高置信度自动选择。
- 记录 workflow 工具结果、成功/失败摘要和交互输出，用于后续诊断和智能调用优化。
- 字幕组偏好会吸收用户改选产生的负反馈，并按时间做近因衰减。
- Mikan 字幕组选定后直接调用 ANI-RSS API 添加订阅。
- 写入 ANI-RSS 前会检查已启用订阅，避免重复提交相同 RSS 或同一 Bangumi/字幕组订阅。
- 已启用订阅列表默认展示前 20 条，并按 ANI-RSS 星期分组渲染。
- RSS 直连添加会先生成确认卡片，确认后再写入 ANI-RSS。
- 交互结果默认渲染为图片卡片；渲染失败会回退为文本。

## 配置

在 AstrBot WebUI 的插件配置中填写：

- `base_url`: ANI-RSS 服务地址，例如 `http://127.0.0.1:7789`
- `api_prefix`: ANI-RSS API 前缀，通常为 `/api`
- `api_key`: ANI-RSS API Key，通过 `api-key` 请求头发送
- `timeout_seconds`: API 请求超时，默认 `30`
- `interaction_timeout_seconds`: 用户交互等待时间，默认 `120`
- `pending_task_ttl_seconds`: 挂起任务保留时间，默认 `86400`
- `subscription_cache_ttl_seconds`: 订阅列表缓存时间，默认 `300`
- `mikan_search_cache_ttl_seconds`: Mikan 搜索缓存时间，默认 `3600`
- `preference_mode`: 偏好学习模式，`off` / `rank` / `auto`，默认 `rank`
- `preference_min_uses`: `auto` 模式允许自动选择前的最少使用次数，默认 `3`
- `storage_cleanup_interval_seconds`: 过期数据清理间隔，默认 `600`
- `render_mode`: 卡片发送模式，`image` / `text` / `both`；图片渲染器不可用时自动回退文本

不要把真实 API Key 写入仓库文件。

挂起任务和短期缓存使用 SQLite，路径遵循 AstrBot 开发文档的插件数据目录规范：
`data/plugin_data/astrbot_plugin_ani_rss/state.sqlite3`。

## 使用

用户优先使用自然语言：

```text
推荐几部本季新番
帮我订阅淡岛百景
查一下淡岛百景有没有字幕组
查看 ANI-RSS 已启用订阅列表
刷新全部订阅
```

候选卡片会带任务 ID。继续挂起流程时使用：

```text
/ani<任务ID前后几位> <序号|确认|取消>
```

命令前缀优先来自 AstrBot 全局 `wake_prefix`。挂起任务短命令也会兼容
`provider_settings.wake_prefix`，用于 `plana ani68d2 1` 这类线上场景。

```text
plana ani<任务ID前后几位> <序号|确认|取消>
```

## 评审边界

- 删除订阅 API 已封装在客户端，用于发布验证和后续维护；当前不暴露用户 workflow，避免自然语言误删真实订阅。
- `plana ani68d2 1` 仅用于挂起任务短命令；普通 `/anirss ...` 显式命令仍遵循 AstrBot 标准命令唤醒。
- AstrBot WebUI 启动横幅在 Windows GBK 控制台中的 emoji 编码报错属于 AstrBot 本体日志输出问题，不影响本插件加载和运行。

## 架构文档

根目录只保留 `main.py` 作为 AstrBot 插件入口，真实插件运行时在 `plugin/`；其他 Python 文件按职责归入 `routing/`、`integrations/`、`workflows/`、`ui/`、`scripts/`。

- `plugin/PLUGIN_RUNTIME.md`: AstrBot 插件类、配置、挂起任务和订阅构建。
- `COMMAND_ROUTING.md`: AstrBot 命令、wake prefix、短任务 ID 路由。
- `integrations/ANI_RSS_API.md`: ANI-RSS API 客户端和接口约束。
- `workflows/WORKFLOW_ARCHITECTURE.md`: 工作流解析、挂起任务和执行编排。
- `ui/CARD_RENDERING.md`: 图片卡片渲染结构。
- `scripts/COMPATIBILITY_LAYER.md`: 旧导入路径兼容层。

`requirements.txt` 记录运行依赖：`aiohttp`、`Pillow`、`pylitehtml`。
