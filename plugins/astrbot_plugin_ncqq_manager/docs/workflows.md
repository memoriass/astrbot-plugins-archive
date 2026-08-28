# Workflow 文档入口

聊天侧优先暴露少量主 workflow。模型先判断用户意图大类，再由主 workflow 根据 `intent` / `scope` 拼接到细分流程；底层 API 调用、权限判断、审批、分支条件都在流程内部完成。

## 核心原则

- 主 workflow 负责聊天场景下的意图大类。
- 细分 workflow 保留直接调用能力，用于确定性调试或模型已经明确知道目标流程时。
- workflow 是完整业务流程，不是单个 API 包装。
- 多面板场景下，优先在参数中带 `manager`，或把目标写成 `manager/instance`。
- 普通用户操作必须经过绑定和 manager 维度权限校验。

## 文档拆分

| 文档 | 内容 |
| --- | --- |
| `docs/workflow-catalog.md` | 主 workflow、细分 workflow、选择规则和调试命令。 |
| `docs/workflow-engine.md` | `workflows/` 模块职责、扩展顺序和多面板约定。 |
| `docs/group-chat-routing.md` | OneBot v11 群聊识别、白名单和工具调用判定。 |
| `docs/approval-model.md` | 审批边界、群内审批回复和执行安全。 |
| `docs/operation-flows.md` | 创建、重登、诊断、健康检查等核心流程图。 |
| `docs/multi-manager-architecture.md` | 多 ncqq-manager 面板配置、权限和 client 生命周期。 |

## 维护规则

- 修改 workflow 名称、参数或路由时，同步 `workflow-catalog.md`。
- 修改模块分工或新增 flow 文件时，同步 `workflow-engine.md`。
- 修改群聊触发条件时，同步 `group-chat-routing.md`。
- 修改审批动作或审批回复规则时，同步 `approval-model.md`。
- 修改核心流程顺序时，同步 `operation-flows.md`。
