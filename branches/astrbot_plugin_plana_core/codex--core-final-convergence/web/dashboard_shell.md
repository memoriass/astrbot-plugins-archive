# Dashboard Shell

`web/` 提供 AstrBot 嵌入 Dashboard API、共享 inspector 和无构建 HTML shell。插件运行时不启动独立 FastAPI/Uvicorn 管理端。

## 文件职责

- `api.py`: 嵌入 Dashboard 基础 handler。
- `admin_api.py`: 主动任务、反馈、scope 和受控维护 handler。
- `diagnostics_api.py`: 聚合诊断 endpoint 的薄 handler。
- `auth.py`: Bot 内部回环访问判定；`api.py` 同时识别 AstrBot Dashboard 已认证插件 Web 上下文。
- `inspectors.py`: Web/debug 共享 payload builder。
- `page.py`: 读取并缓存本地 shell 源文件，注入 API/bridge 模式后返回完整 HTML。
- `shell/template.html`、`shell/styles.css`、`shell/app.js`、`shell/i18n.js`: 无构建页面骨架、设计系统、运行时和翻译。
- `shell/views/*.js`: 工作台、记忆、审批与任务、领域集成、集成与运行、诊断与维护视图。
- `resource_payload.py`: 合并服务治理记录与 201/202 运行态只读探测。
- `integration_catalog.py`: 维护 Adapter 与 capability 的稳定目录，包括参数 schema、结果类型、产物属性和代表性健康探测。
- `integration_payload.py`: 将 202 Adapter Gateway、服务适配器、凭据就绪状态和 capability 探测证据整理为独立集成视图。
- `diagnostics_payload.py`: 将服务、Codex 治理、数据健康和近期审计归并为可操作诊断快照。
- `../pages/dashboard/index.html`: AstrBot 新插件 WebUI 发现入口，负责加载 bridge SDK 并挂载 Core shell。

## API 面

- `GET /plana/api/overview`: 运行状态、表统计、doctor 摘要。
- `GET /plana/api/integrations`: Adapter Gateway、固定服务适配器、凭据状态和 capability readiness。
- `GET /plana/api/resources`、`/remote-tasks`: 资源注册表、主体绑定、权限、别名和 Codex 远程执行只读检查。
- `GET /plana/api/diagnostics`: 面向运维的聚合诊断，区分真实失联、未启用和历史残留，并保留折叠技术附录。
- `GET /plana/api/memories`、`/retrieve-test`、`/context-preview`: 记忆查看和召回验证。
- `GET /plana/api/profile`、`/relations`、`/concepts`: 用户理解和图谱。
- `GET /plana/api/tasks`: TaskSession 路由与领域/Codex 提案轨迹。
- `GET /plana/api/remote-tasks`: Codex Runner 运行、取消和结果状态。
- `GET|POST /plana/api/feedback*`、`/recall-gaps*`: 记忆质量与 recall gap 处理。

## Shell 规则

- 不引入 npm、Vite、React 或外部 CDN；源文件按职责拆分，但由 `page.py` 内联装配以兼容插件页沙箱。
- 静态兼容页保持无外部资源，不新增第二套前端状态。
- 一级入口固定为工作台、记忆、审批与任务、领域集成、集成与运行、诊断与维护。
- 主界面先展示用户能理解的结论与下一步；trace、hash、backend 和原始 JSON 只能放在可展开的“技术详情”中。
- Adapter Gateway 的名称、说明、参数、返回类型、确认边界和探测说明必须使用 `shell/i18n.js` 的稳定 key；API 只返回中立目录字段，不按请求语言复制 payload。
- 领域集成只展示 `domain_harness` 动态发现的独立领域插件。领域详情必须明确插件 owner、profile、direct dispatch 和写确认声明。
- Bridge Gateway 只承担传输，不得在 Web 中显示为 Komga 或其他领域的 owner。未安装领域插件时保持安全空态，不生成 owner、profile 或能力占位；重复 profile/tool 必须在目录中显示告警。
- 能力中心使用列表/详情结构，完整描述是一级信息；ID、路径、契约、扫描和完整性字段只能进入技术详情。
- 宽表必须放入独立横向滚动容器；移动端需要结构性退化，禁止只依赖缩小 padding 或隐藏页面溢出。
- 本地预览使用 `scripts/preview_web.py`，stub 数据只用于 UI 检查，不替代 `/api/plug/plana/*`。
- Shell 仅内联本地模板、样式、脚本和 Logo，不加载远程图片或 CDN。

## 维护规则

- 新 endpoint 必须同步 AstrBot 嵌入 API、页面调用和验证脚本。
- Core Dashboard 不再维护 Plana 登录/session token。
- AstrBot 已认证插件 Web 上下文和本机回环可访问；非回环或带代理转发头且没有 AstrBot 用户上下文的请求返回 401。
- 危险 POST 必须要求 `confirm=true` 或有效的 proposal/lease 确认边界。
- Web shell 结构变更必须通过 `scripts/check_web_shell.py`；新插件 WebUI 入口变更必须通过 `scripts/check_astrbot_embed.py`。

## AstrBot 插件页嵌入链路

- `pages/dashboard/index.html` 不再跳转到 `/api/plug/plana/dashboard`。生产 Dashboard 会先保护 `/api/plug/*`，插件页沙箱直接跳转会丢失插件页 asset token。
- 插件页先加载 `/api/plugin/page/bridge-sdk.js`，再通过 `AstrBotPluginPage.apiGet("dashboard")` 让父页面带 Dashboard JWT 请求 Core。
- 插件页禁止使用 `document.open/write/close` 重写 iframe 文档。AstrBot bridge SDK 的消息监听必须保留，入口只能用 `DOMParser` 解析返回的 shell，并在当前文档中挂载样式、DOM 和运行脚本。
- Core 同时注册 `/plana/*` 和 `/astrbot_plugin_plana_core/*` 两组 Web API。前者保留旧入口；后者供 AstrBot 插件页 bridge 自动拼接 `/api/plug/<pluginName>/...` 使用。
- bridge 模式下 `web/shell/app.js` 使用 `/__plana_bridge_api__` 作为内部 fetch 哨兵，由页面内 fetch adapter 转发到 `AstrBotPluginPage.apiGet/apiPost`。不要把临时凭据放进 URL query。
- AstrBot 插件页 iframe 没有 `allow-same-origin`，`localStorage/sessionStorage` 可能抛出 `SecurityError`。Dashboard shell 必须通过 `storageGet/storageSet` 访问持久化偏好，并在沙箱内退回内存存储。
