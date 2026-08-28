# rendering 模块

`rendering` 定义渲染端口，隔离业务模块和具体 HTML 渲染实现。

## 文件职责

- `renderer_port.py`: 渲染接口协议。
- `html_renderer_adapter.py`: 将 `utils.html_renderer.HtmlRenderer` 适配为端口实现。

## 维护说明

- Handler 和主题渲染应依赖 `RendererPort` 或具体 theme，不直接操作 Playwright。
- 如果未来替换渲染实现，优先在这里加适配器。
- 当前默认输出 PNG，并启用透明背景；需要透明裁剪时优先传具体 selector。
- 业务模块只关心 `render()` 输入输出，不应知道浏览器启动、页面等待或截图细节。
- 新增渲染实现时保持 `RendererPort` 方法签名稳定，再逐步替换调用方注入。
- 渲染失败要向调用方返回明确异常，让 handler/workflow 能给用户可读提示。
