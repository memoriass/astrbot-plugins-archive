# utils 模块

`utils` 放渲染、资源和日志等辅助能力。

## 文件职责

- `html_renderer.py`: Playwright 浏览器生命周期和 HTML 截图。
- `resource.py`: 模板、背景图等资源路径和读取。
- `logger.py`: AstrBot logger 适配器。
- `timezone.py`: Bilibili 时间戳格式化，按 `display_timezone` 展示，默认 `Asia/Shanghai`。
- `renderers/`: 推送卡片主题。
- `resources/`: 内置模板和默认背景图。
- `image_optimizer.py`: 渲染前压缩直播封面、动态 hero 和头像，降低超大主图带来的 Playwright 下载和解码负担。

## 维护说明

- 浏览器生命周期由 `BrowserManager` 管理，关闭逻辑由调度器和插件生命周期触发。
- 模板渲染失败通常会影响用户可见结果，调用方应返回可读错误。
- 新模板应放到 `utils/resources/templates/`。
- `HtmlRenderer` 默认输出透明 PNG；模板外层背景应保持 transparent。
- `html_renderer.py` 是 Playwright 具体实现，业务模块不要绕过 `rendering/` 端口直接依赖它。
- 资源路径统一通过 `resource.py` 获取，避免 Windows/Linux 路径差异。
- 日志适配放 `logger.py`，新增模块优先使用 AstrBot logger，不使用裸 `print()`。
- Bilibili 接口时间戳是 Unix 时间，用户可见卡片必须通过 `timezone.py` 和配置时区格式化，不要直接使用系统本地时区。
