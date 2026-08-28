# 模块结构说明

运行代码按正式插件职责拆分为 `core`、`tools`、`workflows`、`rendering` 四组。

## 目录总览

| 目录 | 面向对象 | 说明 |
| --- | --- | --- |
| `core/` | 底层服务 | 多面板 HTTP 客户端、API 动作、监控查询、审批、健康检查、掉线 POST 接收。 |
| `tools/` | AstrBot 入口 | `main.py` 混入的工具能力，负责把 AstrBot 事件转到底层服务。 |
| `workflows/` | 业务编排 | LLM 和 `/ncqq` 只选择 workflow，由这里串联底层服务。 |
| `rendering/` | 图文渲染 | HTML 模板转图片和降级输出。 |
| `templates/` | 资源模板 | 实例列表、绑定关系、告警图模板。 |
| `pages/` | WebUI 页面 | AstrBot Plugin Pages 静态资源。 |
| `docs/` | 稳定文档 | 架构、workflow、审批、群聊路由、发布合规说明。 |

## 维护边界

- `main.py` 不写具体业务流程，只做 AstrBot 生命周期和入口分发。
- `workflows/` 只编排业务，不直接处理 AstrBot 配置或 KV 存储细节。
- `tools/` 负责兼容既有命令/tool 行为，不新增底层 HTTP 逻辑。
- `core/` 不依赖 `tools/`，避免底层服务反向调用入口层。
- `rendering/` 只处理渲染，不读写审批、绑定或远端状态。
- `pages/` 只放静态页面资源，后端接口放在 `tools/page_api.py`。
- `local-docs/` 和 `docs/current/` 仅存放本地接入测试、当前任务和评审记录，已被 git 排除，不作为正式架构文档来源。

## 新增能力放置规则

| 需求 | 放置位置 |
| --- | --- |
| 新 ncqq-manager API 封装 | `core/actions.py` 或 `core/monitoring.py` |
| 新面板级能力或配置解析 | `core/client.py` 与 `main.py` 的 manager helper |
| 新聊天业务流程 | `workflows/models.py`、`workflows/parsing.py`、对应 flow 文件、`workflows/dispatcher.py` |
| 新 AstrBot 命令或工具混入 | `tools/` |
| 新插件 Skill 包 | `skills/<skill_name>/SKILL.md`，并同步 `docs/astrbot-tools.md` |
| 新 WebUI 页面 | `pages/<page_name>/index.html` 与 `tools/page_api.py` |
| 新 HTML 图片输出 | `rendering/html_renderer.py` 与 `templates/` |
| 新机器对机器回调入口 | `core/` 独立服务模块，并由 `main.py` 生命周期启动；不得注册为 LLM 工具 |
| 新交接或结构说明 | `docs/` 下按架构功能命名的文档 |

## 稳定文档索引

| 文档 | 职责 |
| --- | --- |
| `docs/architecture.md` | 总体架构和文档入口。 |
| `docs/configuration.md` | 插件配置项、示例和安全边界。 |
| `docs/data-storage.md` | KV 数据结构、兼容规则和迁移要求。 |
| `docs/multi-manager-architecture.md` | 多 manager 配置、client、权限和审批边界。 |
| `docs/workflows.md` | workflow 文档入口和同步规则。 |
| `docs/workflow-catalog.md` | workflow 列表、选择规则和调试命令。 |
| `docs/workflow-engine.md` | workflow 模块职责和扩展步骤。 |
| `docs/group-chat-routing.md` | OneBot v11 群聊触发和白名单。 |
| `docs/approval-model.md` | 审批队列、群内审批和执行安全。 |
| `docs/operation-flows.md` | 核心业务流程图。 |
| `docs/core-services.md` | 底层服务层说明。 |
| `docs/astrbot-tools.md` | AstrBot 工具混入层说明。 |
| `docs/rendering-assets.md` | HTML 渲染和素材说明。 |
| `docs/plugin-pages-architecture.md` | AstrBot Plugin Pages 和页面 API 边界。 |
| `docs/plugin-compliance.md` | AstrBot 插件合规和发布复查。 |
| `docs/maintenance-policy.md` | 修改边界、文档同步和大文件限制。 |
