# Dialogue Center

`dialogue/` 是 Plana Core 的会话裁定层，只负责判断当前消息属于陪伴聊天、单一领域插件，还是受控 Codex 任务。它不包含通用 Workflow Registry、能力市场、本地命令执行器或动态 Skill 安装链。

## 当前路径

1. 普通聊天进入 Persona、关系和记忆 prompt，不挂载执行工具。
2. 显式历史检索按请求挂载 `plana_recall_memory`。
3. NCQQ、ANI-RSS、Komga 请求一次只选择一个领域 descriptor，并只开放对应插件工具。
4. 文件、代码、浏览器、多页调查和长耗时操作生成 Codex proposal，由 Core 持有确认与授权边界，经 Bridge 交给原生 Runner。

## 文件职责

- `models.py`：turn context、decision、route 和 intent 类型。
- `entry_filters.py`：AstrBot 主动接管与被动观察入口过滤。
- `actions.py`：本地受控动作目录；复杂执行只产生 `codex_candidate`。
- `analyzer.py`：规则优先的 `DialogueTurnAnalyzer`，模型只能在本地动作目录中提供建议。
- `router.py`：把事件转换为 actor-scoped `TurnContext`。
- `service.py`：组合 wake、行为决策、preflight、领域路由、记忆和任务结果。
- `task_broker.py`：选择单一领域插件或原生 Codex 委派。
- `task_session_service.py`：处理确认、继续、取消、重试和结果续接。
- `domain_contracts.py`：领域插件 descriptor、`OperationProposal` 和策略结果 contract。
- `remote_task.py`：生成不含 Runner URL/token 的 Codex 委派 payload。

## 安全边界

- LLM 不能发明可执行能力，只能选择本地规则或已发现的领域 descriptor。
- 普通聊天不开放 shell、浏览器、通用服务查询或执行移交工具。
- 领域写操作由领域插件返回 proposal，Core 决定是否需要确认并签发执行租约。
- Codex proposal 不能自行确认或扩大 `write_scope`；Bridge 只负责 relay 和结果交付。
- TaskSession 按 `scope_id + actor_id` 隔离，其他群成员不能继承确认权、artifact 或私有上下文。
- 隐藏工具对应的历史 tool call/result 必须成对清理，避免模型从旧上下文绕过本轮工具白名单。

## 快速模型边界

- preflight 默认关闭，仅在配置专用 provider 时参与。
- preflight 只能选择 `actions.py` 已存在的 action；未知 action 被忽略。
- 本地拒绝、状态、记忆写入、领域选择和 Codex 授权边界优先于模型建议。
- preflight 不得回退到默认聊天模型、memory planner 或其他 provider。

## 维护规则

- 新领域能力优先进入领域插件共享业务内核，并通过 descriptor 接入 Core。
- 新的复杂执行类型进入 Codex allowlist，不在 Core 增加本地 command backend。
- 新写操作必须定义 proposal、确认策略、资源范围、结果观察和取消/清理路径。
- 对话层不得直接写 SQL，不得持有 Bridge/Runner 凭据，不得同时挂载多个领域入口。
