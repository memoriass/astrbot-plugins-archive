# astrbot_plugin_komga_manager

独立的 AstrBot Komga 管理插件。插件提供统一的 `komga_manager` Agent 工具和 `/komga` 调试命令，用自然语言或明确 workflow 查询 Komga。

## 能力

只读 workflow 会直接访问 Komga：

- `list_libraries`：列出书库。
- `list_recent`：列出最近更新书籍。
- `search_series`：按名称搜索系列。
- `series_detail`：查看系列详情。
- `list_books`：列出系列内书籍。
- `on_deck`：列出待继续阅读书籍。
- `collections`：列出合集。
- `readlists`：列出阅读列表。

写 workflow 永远只生成 `write_pending` 提案，不调用 Komga 写接口：

- `scan_library`
- `analyze_library`
- `refresh_library_metadata`
- `refresh_series_metadata`

## 配置

在 AstrBot 插件配置中填写：

- `base_url`：Komga 地址，默认 `http://127.0.0.1:25600`。
- `api_key`：优先使用的 API Key。
- `username` / `password`：未设置 API Key 时使用 Basic Auth。
- `allow_public_url`：默认关闭，避免把凭据发送到意外公网地址。
- `timeout_seconds`、`default_limit`：请求超时和默认分页大小。

URL 中不允许内嵌用户名或密码。日志和回复不会输出凭据。

## 使用

Agent 工具示例：

```text
workflow=ai_dispatch target=看看 Komga 有哪些书库
workflow=search_series target=葬送的芙莉莲
workflow=series_detail params={"series_id":"..."}
```

命令示例：

```text
/komga list_libraries
/komga search_series 葬送的芙莉莲
/komga series_detail <series_id>
/komga scan_library <library_id>
```

最后一条只返回待确认提案，不执行扫描。

## 验证

```text
python -m unittest discover -s tests -v
python scripts/check_workflow_integration.py
python -m compileall -q .
git diff --check
```

