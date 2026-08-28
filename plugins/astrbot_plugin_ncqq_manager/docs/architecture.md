# ncqq_manager 架构说明

本文面向后续模型和维护者，说明正式插件结构。代码中只保留必要短注释，模块职责以本文和 `docs/` 下按功能命名的架构文档为准。

## 根目录

| 路径 | 职责 |
| --- | --- |
| `main.py` | AstrBot 插件类入口，注册 LLM 工具、`/ncqq` 命令、群白名单、管理员判断、用户绑定、审批快捷回复和内部服务生命周期。 |
| `__init__.py` | 导出插件类。 |
| `metadata.yaml` | AstrBot 插件元信息。 |
| `_conf_schema.json` | AstrBot 配置项定义。 |
| `logo.png` | 插件展示图标，保持 1:1。 |
| `requirements.txt` | AstrBot 环境之外的 Python 依赖。 |

## 运行代码目录

| 目录 | 职责 |
| --- | --- |
| `core/` | ncqq-manager HTTP 客户端、底层 API 动作、监控查询、审批 KV、健康检测、掉线 POST 接收和二维码交互。 |
| `tools/` | AstrBot 工具混入，承接命令和 LLM 入口调用。 |
| `workflows/` | 面向聊天侧的业务 workflow 编排，只暴露明确 workflow ID。 |
| `rendering/` | HTML 模板转图片能力。 |
| `templates/` | HTML 渲染模板。 |
| `pages/` | AstrBot Plugin Pages 静态资源，当前提供多面板看板和审批入口。 |

`main.py` 只连接 AstrBot 生命周期和入口；业务选择走 `workflows`，底层服务走 `core`，图文输出走 `rendering`，WebUI 页面走 `pages` 和 `tools/page_api.py`。

## 多 Manager 模型

插件支持多个 ncqq-manager 面板。配置入口统一为 `_conf_schema.json` 中的 `manager_profiles` 模板列表，每个面板以稳定 `manager_id` 管理独立 HTTP session。

命名规则：

- 面板 ID 只保留字母、数字、`-`、`_`，其他字符会规范化。
- 未显式指定时使用 `default_manager`。
- 绑定关系使用 `manager/instance` 存储，旧的纯实例名绑定只在默认面板继续兼容。
- 聊天目标可以直接写成 `cloud/mybot`，也可以在参数里写 `manager=cloud`。

多面板只表示多个 ncqq-manager 控制面板；BotShepherd/radar endpoint 仍属于各自面板内部的后端端点，不与 manager 概念混用。

## Workflow 层

聊天侧只暴露 workflow，不直接暴露底层 API 包装。优先使用主 workflow：`manage_instance`、`query`、`manage_backend`、`review_approvals`；细分 workflow 仍可直接调用，并作为主流程内部路由目标。健康能力不进入 workflow 注册表。

对外入口从 `workflows` 导入：

- `workflow_from_tool()`
- `workflow_from_cli()`
- `run_ncqq_workflow()`

`workflows/dispatcher.py` 是稳定调度入口，具体实现分到：

- `models.py`：workflow 元数据、请求模型、动作别名集合。
- `parsing.py`：LLM 工具参数和 `/ncqq` 命令参数解析。
- `common.py`：HTTP 读取、容器状态、布尔和时间等通用工具。
- `formatters.py`：workflow 文本输出格式化。
- `access.py`：目标实例解析、权限检查、后端别名解析、用户绑定写入。
- `instance_flows.py`：创建、重登、控制、接后端、实例检测、删除流程。
- `admin_flows.py`：综合健康、Bot 状态、消息、审计、资源、配置读取流程。

新增 workflow 时按顺序改：

1. 在 `workflows/models.py` 添加 `CompiledWorkflow`。
2. 在 `workflows/parsing.py` 添加 CLI 参数解析规则。
3. 在合适的 flow 模块实现 `_run_xxx()`。
4. 在 `workflows/dispatcher.py` 调度分支接入。
5. 更新 `docs/workflow-catalog.md`。
6. 若流程顺序变化，同步 `docs/operation-flows.md`。

## 权限与审批

管理员判断统一使用 `NCQQManagerPlugin.is_plugin_admin()`，其规则是 AstrBot role admin 或全局 `admins_id` 命中。

高权限用户侧操作必须进入审批队列：

- `create_instance`
- `delete`
- `inject_backend`

审批记录存放在插件 KV 的 `pending_approvals`，处理时使用 `core.approval.claim_approval()` 原子领取。管理员可以通过 `review_approvals` workflow 处理，也可以在群里用明确的审批回复处理。

## 健康与监控

健康聚合只保留给内部代码、Plugin Pages 和定时监控，不通过自然语言 LLM 工具或 `/ncqq` 外部命令暴露，也不注册到 `COMPILED_WORKFLOWS`。历史健康 ID：

- `check_health`
- `check_manager`
- `check_botshepherd`
- `check_bot_runtime`

只用于公开入口识别并阻断，不进入 workflow 调度。公开入口必须直接忽略或拒绝健康类调用，避免承接通用系统、其他插件或外部服务的健康检查。健康聚合只覆盖 ncqq-manager 管理器健康、BotShepherd 状态、Bot runtime、容器列表和后端端点，后端端点读取失败应显示 WARN。

ncqq-manager `plugin_api` 掉线 POST 由 `core/offline_webhook.py` 的独立 aiohttp 接收器处理。它不注册为 LLM 工具，也不注册到 Plugin Pages API；入口只接受机器对机器 POST，并把事件落到 `health_snapshot` 后复用 `core/health_check.py` 的通知函数。

## 文档维护

- `docs/module-map.md` 是新目录结构索引。
- `docs/configuration.md` 说明 `_conf_schema.json` 配置项和安全边界。
- `docs/data-storage.md` 说明插件 KV key、绑定结构、审批记录和健康快照。
- `docs/multi-manager-architecture.md` 说明多 ncqq-manager 面板模型。
- `docs/core-services.md` 说明底层服务层。
- `docs/astrbot-tools.md` 说明 AstrBot 工具混入层。
- `docs/workflow-engine.md` 说明 workflow 编排层。
- `docs/workflow-catalog.md` 说明 workflow 列表、选择规则和调试命令。
- `docs/group-chat-routing.md` 说明 OneBot v11 群聊路由和白名单。
- `docs/approval-model.md` 说明审批边界和群内审批处理。
- `docs/operation-flows.md` 说明核心操作流程图。
- `docs/rendering-assets.md` 说明渲染和资产。
- `docs/plugin-pages-architecture.md` 说明 AstrBot WebUI 页面和 Page API 边界。
- `docs/workflows.md` 是 workflow 文档入口。
- `docs/plugin-compliance.md` 记录 AstrBot 插件结构与发布合规检查。
- `docs/maintenance-policy.md` 记录修改边界、文档同步和大文件限制。

本地接入测试、评审计划、临时分析记录放在根目录 `local-docs/` 或 `docs/current/`，这两个目录进入 `.gitignore`，不随正式版本归档。需要长期保留给后续模型接手的内容，应整理进上述功能命名文档，而不是提交临时记录。
