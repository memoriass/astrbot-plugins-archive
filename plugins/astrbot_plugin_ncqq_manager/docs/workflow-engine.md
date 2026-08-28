# Workflow Engine

`workflows` 是 LLM 和 `/ncqq` 的业务编排层。聊天侧优先使用主 workflow，细分 workflow 保留直接调用能力。

所有 workflow request 都携带可选 `manager_id`。解析层接受 `manager`、`manager_id`、`panel`、`site` 参数；访问层同时支持 `manager/instance` 目标写法。

| 文件 | 职责 |
| --- | --- |
| `workflows/__init__.py` | 对外导出稳定 workflow API。 |
| `workflows/dispatcher.py` | workflow 调度入口。 |
| `workflows/models.py` | workflow 元数据、请求模型、动作别名。 |
| `workflows/parsing.py` | LLM 工具参数和 `/ncqq` CLI 参数解析。 |
| `workflows/common.py` | 低层通用读取、容器状态、布尔/时间格式工具。 |
| `workflows/formatters.py` | workflow 输出文本格式化。 |
| `workflows/access.py` | 目标实例、权限、后端别名、绑定关系辅助。 |
| `workflows/instance_flows.py` | 实例创建、重登、控制、接后端、检测、删除。 |
| `workflows/admin_flows.py` | 内部健康 helper、消息、审计、资源、配置读取。 |

## 主流程

| workflow | 路由参数 | 目标 |
| --- | --- | --- |
| `manage_instance` | `intent=create/recover/control/connect/check/list/delete` | 实例相关主入口。 |
| `query` | `scope=instances/backends/instance/messages/audit/resources/config` | 查询类主入口。 |
| `manage_backend` | `intent=list/check/connect` | 后端端点主入口。 |
| `review_approvals` | `action=list/approve/reject` | 审批主入口。 |

健康聚合不属于公开 `query` 范围，也不注册到 `COMPILED_WORKFLOWS`；Plugin Pages 和定时监控直接调用内部健康代码。

## 多面板约定

- 进入具体实例流程前必须经过 `workflows/access.py` 的目标解析。
- 任何读取 `/api/...` 的 helper 都要接收 `manager_id` 并调用 `client_for_manager()`。
- 审批参数必须保存 `manager_id`，批准执行时不可回退到默认面板。
- 用户绑定、权限校验和健康快照统一使用 `manager/instance`。

新增 workflow 顺序：

1. `workflows/models.py` 注册 workflow。
2. `workflows/parsing.py` 增加 `/ncqq` 参数解析。
3. 在 `workflows/instance_flows.py` 或 `workflows/admin_flows.py` 实现流程。
4. `workflows/dispatcher.py` 接入调度。
5. 更新 `docs/workflow-catalog.md`。
6. 若流程顺序变化，同步 `docs/operation-flows.md`。
