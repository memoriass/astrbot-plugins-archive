# Plugin Runtime

AstrBot 插件运行时支撑模块。由于 AstrBot loader 以根目录 `main.py` 作为插件类发现边界，`AniRssPlugin` 类保留在 `main.py`；具体运行职责在本目录拆分。

## 文件

- `settings.py`: 插件配置读取、ANI-RSS client、wake prefix、渲染配置。
- `storage_paths.py`: 按 AstrBot 规范解析插件数据目录。
- `sqlite_store.py`: SQLite 运行时存储，负责挂起任务、缓存和定时清理。
- `pending_store.py`: 挂起任务创建、短 ID 匹配和任务读取。
- `cache_store.py`: ANI-RSS 订阅列表、Mikan 搜索和字幕组列表短期缓存。
- `preferences.py`: 当前会话常用字幕组和语言偏好学习，用于字幕组候选排序或自动选择。
- `tool_results.py`: workflow 执行结果记忆，记录成功/失败摘要和交互输出。
- `subscription_builder.py`: RSS 类型识别、Mikan bgmUrl 补齐、订阅结构构造。
- `tooling.py`: 工具调用事件提取、自然语言提示修正、帮助文本。

## 数据

运行数据写入 AstrBot 数据目录：

```text
data/plugin_data/astrbot_plugin_ani_rss/state.sqlite3
```

`pending_task_ttl_seconds` 控制挂起任务保留时间；`subscription_cache_ttl_seconds`
控制订阅列表缓存时间；`mikan_search_cache_ttl_seconds` 控制 Mikan 搜索和字幕组缓存时间；
`preference_mode` 控制偏好学习策略；工具结果默认保留 90 天；`storage_cleanup_interval_seconds`
控制定时清理间隔。插件重载不会丢失未过期挂起任务、偏好数据和工具结果记忆。
