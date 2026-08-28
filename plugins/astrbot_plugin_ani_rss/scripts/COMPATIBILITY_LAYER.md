# Compatibility Layer

兼容层，保留早期拆分前的导入路径。

## 文件

- `api.py`: 从 `integrations.ani_rss` 重新导出 API 客户端。
- `rendering.py`: 从 `ui.rendering` 重新导出渲染入口。
- `workflows.py`: 从 `workflows` 重新导出 workflow 入口。

新代码应直接从 `integrations/`、`workflows/`、`ui/` 导入。
