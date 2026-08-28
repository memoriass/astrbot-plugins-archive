# AstrBot Tools

`tools` 存放 `main.py` 混入的 AstrBot 工具能力，负责接收事件参数并调用 `core`。

AstrBot 的 LLM 工具来自插件代码注册，不读取 `docs/*.md` 作为工具集。本插件由 `main.py` 暴露统一工具 `ncqq_manager`，具体实例、后端、审批能力通过 workflow 参数路由到 `tools/` 和 `workflows/`。

## Tool 与 Skill 边界

- `@llm_tool` 注册的是可执行工具，本插件当前只有 `ncqq_manager` 一个公开 LLM 工具。
- `docs/*.md` 只给维护者和后续模型阅读，AstrBot 不会把它们自动注册成工具。
- AstrBot 支持插件携带 `skills/` 目录给 LLM 提供知识或提示词，但本插件当前不提供 Skill 包。
- 后续若新增 Skill，放在 `skills/<skill_name>/SKILL.md`，并同步 `docs/plugin-compliance.md` 和 `docs/module-map.md`。

## LLM 工具触发边界

`ncqq_manager` 只处理明确提到 ncqq、NapCatQQ、ncqq-manager、BotShepherd、OneBot、已配置面板或已绑定 NapCatQQ 实例的请求。它不得承接 AstrBot 自身、模型提供商、其他插件、网站、服务器、Docker 通用服务或未知对象的健康检查。

健康能力不注册为对外 workflow，也不开放给自然语言 LLM 工具调用或 `/ncqq` 外部命令。Plugin Pages 和定时监控直接调用插件内部健康代码。旧的 `check_health`、`check_manager`、`check_botshepherd`、`check_bot_runtime` 以及 `query scope=health/manager/botshepherd/runtime` 写法只用于公开入口识别并阻断，不进入 workflow 调度。来自 LLM tool 的健康类调用会被直接忽略，不输出健康检查结果，避免拦截任何通用“健康检查”请求。

| 文件 | 职责 |
| --- | --- |
| `tools/instance.py` | 实例列表、动作、二维码、监控、文件、绑定关系展示。 |
| `tools/backend.py` | 后端端点注入和审批入口。 |
| `tools/admin.py` | 审批列表、批准、驳回和已批准动作分发。 |
| `tools/page_api.py` | Plugin Pages 后端 API，提供看板汇总和审批处理。 |

维护约定：

- 新增聊天侧业务优先放到 `workflows`，不要在这里堆长流程。
- 这里可以保留已有工具行为的兼容层，但不得新增旧命令别名体系。
- 管理员判断统一调用插件实例的 `is_plugin_admin()`。
- 所有实例、后端、二维码和审批执行入口都要接收或解析 `manager_id`，并通过 `client_for_manager()` 调用目标面板。
- Page API 不新增高权限业务路径；审批批准复用 `_dispatch_approved_action()`。
