# utils resources 模块

`utils/resources` 放渲染所需资源。

## 文件职责

- `templates/`: Jinja2 HTML 模板。
- `backgrounds/`: 默认背景图。
- `fonts/`: Playwright 卡片渲染使用的内置字体。

## 维护说明

- 这里服务推送和命令卡片渲染。
- 资源路径由 `utils/resource.py` 读取，不要在业务模块硬编码绝对路径。
- 模板、字体和背景资源职责分离；新增模板放 `templates/`，新增内置字体放 `fonts/`，新增默认背景放 `backgrounds/`。
- WebUI 页面资产放 `pages/manager/assets/`，不要放到本目录。
