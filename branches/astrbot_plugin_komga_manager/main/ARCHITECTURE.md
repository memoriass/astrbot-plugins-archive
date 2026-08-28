# Architecture

## Boundaries

- `main.py` 只负责 AstrBot 注册、生命周期、工具和命令入口。
- `integrations/komga.py` 负责 URL 校验、认证、HTTP GET、响应拆包与安全字段裁剪。
- `workflows/` 负责请求解析、自然语言路由、只读执行、输出格式和写提案。
- `plugin/` 放置配置与 AstrBot 工具边界辅助代码。
- `scripts/` 与 `tests/` 提供静态契约和行为回归。

## Read Boundary

仅以下 operation 可触发网络请求，且客户端只实现 GET：

`list_libraries`、`list_recent`、`search_series`、`series_detail`、`list_books`、`on_deck`、`collections`、`readlists`。

网络错误必须返回明确错误，不得伪装为空结果。分页大小限制为 1-100。

## Write Boundary

`scan_library`、`analyze_library`、`refresh_library_metadata`、`refresh_series_metadata` 只经过 `workflows/proposals.py` 生成结构化 `write_pending` 提案。独立插件不实现 Komga POST/PUT/DELETE，也不持久化或自动确认写请求。

## Optional Domain Harness

`main` 分支不包含 Plana descriptor。`codex/domain-harness` 分支通过插件本地模块提供可选 `domain_harness_descriptors()` 与 `propose_domain_action()`；该模块只返回普通字典，不导入 Plana Core。

