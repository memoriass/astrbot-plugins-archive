# pages 模块

`pages` 放 AstrBot Plugin Pages 前端静态文件。每个一级目录是一页，必须包含 `index.html` 才会被 AstrBot Dashboard 扫描。

## 当前页面

- `manager/`: Bilibili Push 管理面板，详见 `manager/manager.md`。

## 维护说明

- 页面只通过 `window.AstrBotPluginPage` bridge 调用后端 API。
- 不手写 `/api/plug/...` 绝对路径。
- 不直接读取 Dashboard cookie、LocalStorage 或同源 DOM。
- 不放聊天 help 内容；聊天侧的自然语言能力交给 AI workflow。
- 无构建步骤，静态资源保持相对路径。
- 新增页面时建立独立目录并提供 `index.html`，同时更新 `scripts/check_astrbot_embed.py`。
- 页面静态资源应放在所属页面目录下，避免与推送卡片模板混放。
- 嵌入 AstrBot iframe 后交互空间有限，危险操作统一走页面内确认弹窗。

## AstrBot 嵌入契约

- 每个页面目录必须有 `index.html`，当前只有 `manager/`。
- AstrBot 会注入 `/api/plugin/page/bridge-sdk.js`，页面自身不主动引用 bridge SDK。
- JS 只调用 `window.AstrBotPluginPage.apiGet(endpoint)` 和 `apiPost(endpoint, body)`，endpoint 使用相对名，例如 `overview`、`subscriptions/update`。
- 嵌入契约由 `scripts/check_astrbot_embed.py` 覆盖；如果 AstrBot Plugin Pages 实现变更，先更新该脚本和本模块文档。
