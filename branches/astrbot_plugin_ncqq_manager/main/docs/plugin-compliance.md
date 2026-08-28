# AstrBot 插件合规基线

依据：AstrBot 开发文档 `dev/star/plugin-new.html` 与插件发布说明。

## 结构要求

插件发布包应保持以下结构和字段：

| 项目 | 要求 |
| --- | --- |
| `metadata.yaml` | 位于插件根目录，包含 `name`、`display_name`、`author`、`desc`、`short_desc`、`version`、`repo`。 |
| `astrbot_version` | 声明兼容范围，避免在未验证的 AstrBot 版本中加载。 |
| `support_platforms` | 声明 `aiocqhttp`，按 OneBot v11 标准消息使用，不考虑 WeChat adapter。 |
| `main.py` | 插件主类入口；`@register(...)` 的作者、版本、仓库地址与 `metadata.yaml` 对齐。 |
| `__init__.py` | 导出插件类，保留包入口。 |
| `_conf_schema.json` | 使用 AstrBot 支持的 `string`、`bool`、`int`、`template_list` 类型；多面板通过 `manager_profiles` 模板列表配置。 |
| `logo.png` | 根目录正式插件图标，保持 1:1 透明 PNG。 |
| `requirements.txt` | 声明运行时外部依赖。 |
| `pages/` | 可选。当前提供 `ncqq-dashboard/index.html`，用于 WebUI 多面板看板和审批。JS 按 `dashboard-utils.js`、`dashboard-renderers.js`、`app.js` 拆分，样式按 `layout.css`、`cards.css`、`glass.css`、`stage.css`、`detail.css` 拆分，避免页面文件继续膨胀。 |
| `skills/` | 可选。仅在需要随插件提供 LLM 知识或提示词时新增；不把 `docs/*.md` 作为 Skill 来源。 |
| 日志入口 | 插件模块统一使用 `astrbot.api.logger`。 |
| 大文件限制 | Python、Markdown、JSON、YAML、HTML 文件均低于 500 行。 |
| 发布包清洁度 | 不提交 Python 缓存、日志、本地配置、临时文档和未使用候选资产。 |

当前 beta 版本号为 `2.2.0-beta.4`，`metadata.yaml` 与 `main.py` 的 `@register(...)` 必须保持一致。

## Plugin Pages 边界

Plugin Pages 用于独立 WebUI。当前页面只覆盖多面板只读看板和审批批准/拒绝；简单配置继续使用 `_conf_schema.json`。页面通过 `window.AstrBotPluginPage` bridge 调用相对 endpoint，不硬编码 `/api/plug/`，不使用 Cookie、localStorage 或 sessionStorage 保存状态。后端 API 使用 `quart.jsonify`、`quart.request` 和 AstrBot `context.register_web_api()`，主前缀跟随 metadata 插件名 `ncqq_manager`，并兼容目录名 `astrbot_plugin_ncqq_manager`；不得依赖未公开的 `astrbot.api.web` 封装。

## 结构约定

- 插件入口层保持在根目录：`main.py`、`__init__.py`、`metadata.yaml`、`_conf_schema.json`、`logo.png`。
- 运行代码按 `core/`、`tools/`、`workflows/`、`rendering/` 分层。
- Plugin Pages 页面资源放入 `pages/`，后端 API 放入 `tools/page_api.py`，并同步 `docs/plugin-pages-architecture.md`。
- 若后续新增插件 Skill，资源放入 `skills/`，并说明它与 `@llm_tool` 的调用边界。
- 面向后续模型接手的说明放在 `docs/architecture.md`、`docs/module-map.md` 和按架构功能命名的文档中，代码内只保留必要短注释或 docstring。
- 根目录保留唯一 `README.md`。
- 本地接入测试和当前任务记录放入 `local-docs/` 或 `docs/current/`，两者均被 git 排除，避免临时文档反复刷写正式提交。
- 发布前清理未被页面或渲染模板引用的候选图、预览图和旧背景图。

## 发布复查

发布或同步到远端前执行：

```powershell
python -X utf8 -m compileall main.py core tools workflows rendering
python -X utf8 scripts/verify_release.py
python -X utf8 -c "import json; json.load(open('_conf_schema.json', encoding='utf-8')); print('json ok')"
python -X utf8 -c "import sys, pathlib; sys.path.insert(0, str(pathlib.Path('..').resolve())); import astrbot_plugin_ncqq_manager.main; print('import ok')"
node --check pages/ncqq-dashboard/app.js
node --check pages/ncqq-dashboard/dashboard-renderers.js
node --check pages/ncqq-dashboard/dashboard-utils.js
git diff --check
```
