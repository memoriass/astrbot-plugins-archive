# backgrounds 模块

`utils/resources/backgrounds` 放插件内置背景图。

## 维护说明

- 首次启动时会复制到 AstrBot 数据目录下的插件背景目录。
- 新增背景图只放静态图片，不放生成脚本或临时文件。
- 背景资源用于推送卡片兼容路径；透明卡片模板不应依赖背景图。
- 删除或改名背景图前检查 `core/runtime.py` 的初始化复制逻辑。
