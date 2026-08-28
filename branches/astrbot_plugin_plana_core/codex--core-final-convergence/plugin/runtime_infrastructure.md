# Runtime Infrastructure

`plugin/` 保存 Plana Core 的 AstrBot 运行时基础设施。入口文件只装配这些组件，不直接承载业务逻辑。

## 文件职责

- `config.py`: 将 AstrBot 分组配置和旧平铺配置规整为 runtime dict。
- `db.py`: SQLite 连接 wrapper。
- `models.py`: 对外 re-export 共享模型。
- `runtime.py`: 初始化存储、记忆、workflow、任务、关系、附属 client、后台 job 和 feature flags。
- `runtime_ops.py`: 维护、备份、索引、scope 和状态类运行时操作。
- `runtime_labels.py`: 运行状态和风险等级的展示标签。
- `storage.py`: Core storage facade。
- `safety.py`: 写入和风险操作安全门。
- `voice.py`: Plana TTS 附属插件只读调用 client。
- `gallery.py`: Plana Gallery 本机候选、resolve 和反馈 client；只接受 loopback URL，并校验返回路径位于 Gallery 数据目录。
- `livingmemory_compat.py`: `/lmem` 兼容命令映射。
- `plugin_web.py`: Dashboard API、LLM recall tool 和 secretary tool 注册 mixin。
- `plugin_events.py`: AstrBot 装饰器薄包装对应的事件实现；装饰方法仍必须直接定义在 `PlanaCorePlugin`，避免继承方法不被框架扫描。
- `plugin_bridge.py`: Bridge API、debug API 和 proactive pickup/delivery薄入口。
- `plugin_bridge_support.py`: Bridge 结果轮询、规范化和投递辅助实现。
- `service_query.py`: 已注册内部服务只读查询的 service/capability/argument 白名单和别名规范化。
- `plugin_lifecycle.py`: 后台 job、资源释放和工具卸载 mixin。

## 维护规则

- `main.py` 不新增业务逻辑；新增装配放入 `plugin/plugin_*.py` 或 runtime facade。
- Runtime 只组装服务，不把跨域业务策略写成大分支。
- 新配置必须同步 `_conf_schema.json`、README、`ARCHITECTURE.md` 和检查脚本。
- 附属插件 client 只允许同机回环 URL；除 Bridge Gateway 外，不再提供跨主机 token/header 配置。Gallery 模型选择属于 Core 内部 advisory 步骤，不能构造 `asset_ref`、路径或副作用。
- 请求级 ToolSet 必须通过 AstrBot 公开 `ToolSet` 构造。历史中只保留允许且拥有对应 tool result 的调用；孤立 tool call 转为普通文本或删除，不能再次发送给 provider。
