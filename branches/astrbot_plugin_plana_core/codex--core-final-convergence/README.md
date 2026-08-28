# Plana Core

Plana Core 是 AstrBot 内的陪伴中枢。它负责陪伴对话上下文、Persona、关系、记忆策略、领域插件选择、写操作确认、Codex 授权评审和结果交付，不再承担通用工具市场或通用工作流中心职责。

## 当前边界

保留：

- 陪伴聊天、Persona、关系与 Gallery 反应图协同。
- 自动记忆召回，以及显式历史搜索时的请求级 Recall 工具。
- NCQQ、ANI-RSS、Komga 领域插件的单入口选择；一次请求最多挂载一个领域工具。
- `OperationProposal`、确认账本、执行租约、任务状态和审计。
- Memory Warehouse 的 sibling service / loopback HTTP evidence contract。
- 复杂任务经 Bridge 进入 202 原生 Codex Runner。

不再提供：

- 全局 Secretary、通用服务查询或模型自调用执行移交工具。
- 动态 Skill 安装、自动学习、运行时能力审批或外部 Workflow Center。
- TTS 输出与 Hermes 执行链。

## 运行链路

1. 普通聊天只注入陪伴 prompt 与自动召回记忆，不挂载执行工具。
2. 明确历史检索只挂载 `plana_recall_memory`。
3. Core 识别 NCQQ、ANI-RSS 或 Komga 后，只挂载对应领域插件入口。
4. 领域插件直接完成只读操作；写操作返回受控 proposal，由 Core 评审并请求最终确认。
5. 浏览器、多页调查、代码修改和长任务由 Core 生成 Codex proposal，经确认后交给 Bridge。
6. Bridge 使用 `plana.codex.runner.v1` 与 202 Runner 通信，结果和 artifact 回到原会话。

## 独立组件

- `astrbot_plugin_plana_memory_warehouse`：独立 evidence 数据库，contract 为 `plana.memory_warehouse.v1`。
- `astrbot_plugin_plana_bridge_gateway`：消息交付与 Codex relay。
- `astrbot_plugin_plana_gallery`：陪伴反应图。
- `astrbot_plugin_ncqq_manager`、`astrbot_plugin_ani_rss`、`astrbot_plugin_komga_manager`：领域 owner。
- `plana-service-gateway`：领域插件使用的受控服务适配层。
- `plana-renderer-service`：结构化结果渲染。
- 202 `plana-codex-runner.service`：唯一复杂任务执行器。

## 领域插件分支模型

领域插件采用同一仓库的两条分支，不发布两个插件版本，也不复制两套业务代码：

- `main`（公开分支）：保持独立 AstrBot 使用方式，自行完成原有交互闭环。
- `codex/core-governed`：在共享业务内核之上增加 Plana 接管接线。

两条分支共享实体解析、查询、领域规则和服务访问内核。分支差异只允许出现在 descriptor、proposal/lease adapter、确认接线和通知接线；领域业务逻辑不得分叉。

## 配置重点

- `core.enabled`：总开关。
- `memory_warehouse.*`：Warehouse URL、超时和 push 类型。
- `execution.assistant_remote_runner_enabled`：允许 Core 生成 Codex 委派 proposal；Runner 地址和鉴权只配置在 Bridge。
- `execution.assistant_service_gateway_*`：领域适配网关健康与资源治理连接。
- `gallery_media.*`：Gallery sibling service。
- `ops_bridge.*`：Dashboard 和 Bridge fallback。

## Dashboard

AstrBot 插件页挂载六个主视图：工作台、记忆、审批与任务、领域集成、集成与运行、诊断与维护。任务页只展示 TaskSession、领域路由轨迹与 Codex 运行记录；退役 Workflow 和候选接口不再在线提供。

## 验证

```powershell
C:\git\AstrBot\.venv\Scripts\python.exe scripts\check_code_acceptance.py --tier code
C:\git\AstrBot\.venv\Scripts\python.exe C:\git\astrbot_plugin_plana_bridge_gateway\scripts\check_bridge_gateway.py
C:\git\AstrBot\.venv\Scripts\python.exe C:\git\astrbot_plugin_plana_memory_warehouse\scripts\check_memory_warehouse_plugin.py
```

`code` 层不访问外部服务，包含 compileall、Ruff 未使用引用、JS 语法、文档引用、收敛边界、配置与 `git diff --check`。真实 Runner、201 插件和 Matcha 回归属于后续 integration/live 验证。

## 数据安全

- Memory Warehouse 保持独立数据库，不迁入 Core。
- 退役表和旧执行记录必须先由 `scripts/archive_retired_state.py` 导出、校验并备份，再从活动数据库移除。
- 真实数据库归档只进入 `C:\git\_retired_plana_ecosystem\private-data`，不得推送 GitHub。
- 日志不得输出 token、cookie、完整凭据或完整业务上下文。
