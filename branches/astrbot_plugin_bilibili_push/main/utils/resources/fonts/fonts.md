# fonts 模块

`utils/resources/fonts` 放插件内置渲染字体。

## 当前字体

- `noto-sans-sc-chinese-simplified-400-normal.woff2`: Noto Sans SC 简中常规字重。
- `noto-sans-sc-chinese-simplified-700-normal.woff2`: Noto Sans SC 简中加粗字重。
- `NotoSansSC-LICENSE.txt`: Noto Sans SC 字体许可证。

字体文件来自 `@fontsource/noto-sans-sc@5.2.9`，仅保留简中 400/700 两个 WOFF2 文件，避免把完整多语种、多字重字体包带进插件。

## 维护说明

- 模板通过 `utils/resource.py` 注入 `@font-face`，不要在模板里写外部字体 URL。
- 渲染器通过 Playwright route 从插件目录返回字体文件，不走公网。
- 如果新增字重或替换字体，必须同步 `utils/resource.py` 的字体文件表和许可证文件。
