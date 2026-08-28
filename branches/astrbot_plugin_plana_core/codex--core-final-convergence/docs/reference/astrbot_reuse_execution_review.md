# AstrBot 能力复用优先执行计划

## 原则

Plana Core 继续保持 AstrBot 框架内秘书中枢定位。新增能力先判断 AstrBot 是否已有稳定能力可复用；只有在 AstrBot 没有对应能力、接口不稳定或复用会破坏 Plana 的治理边界时，才在插件内部自建最小实现。

## 复用矩阵

| 能力域 | AstrBot 可复用项 | Plana 处理方式 | 自建触发条件 |
| --- | --- | --- | --- |
| Skill 系统 | `SkillManager`、全局 skills、插件 `skills/<skill>/SKILL.md`、active 状态、persona skills | 只读 adapter，转成 recipe 候选 | AstrBot 未安装或接口不可用时扫描本插件 `skills/` |
| LLM/多模型 | AstrBot provider、provider lookup、LLM tool 注册 | 复用 provider，advisor 只输出 draft/review | provider 缺失时使用本地规则 fallback |
| Web/API | AstrBot Web API 注册、独立 FastAPI 已有管理端 | 嵌入面板和独立端共用 runtime/service | 仅对 Plana 独有 workflow/detail 视图自建 |
| 配置 | AstrBot `_conf_schema.json` 插件配置 | 通过 `plugin/config.py` 规整旧平铺和新分组 | 无框架字段表达能力时才内部默认 |
| 持久化 | 插件自有 SQLite 仍是 Plana 长期业务数据边界 | 继续使用现有 storage facade | 不把长期业务数据散落到临时缓存 |
| 插件市场/pack | AstrBot 插件生态与 Skill 分发 | 先不做远程市场，只做本地 capability pack 目录 | 需要组合 Plana capability 且 AstrBot 无 recipe 目录时自建 |
| Sandbox/runner | AstrBot sandbox/computer skill 元数据可读 | 只读识别 sandbox-only skill 和推荐姿态 | 需要真实隔离时必须外置 sidecar/container/remote runner |
| 网关/入口 | AstrBot command、LLM tool、Web API、Bridge | 统一 surface registry 和 toolset view | 不复制多平台 gateway |

## 大步骤与 Git 保存点

### P43-01 计划与复用边界

- 固化本计划书。
- 明确 Workflow Center sibling 不是当前 git 仓库，Core 只能提交自身变更。
- 保存点：提交计划文档。

### P43-02 Astr Skill/Recipe 复用闭环

- 让 `skill_adapter.py` 暴露可验证的 status 与 recipe candidate。
- 增加本插件 `skills/plana-secretary-workflows/SKILL.md`，让 AstrBot SkillManager 可发现 Plana 的说明型 skill。
- 增加验证脚本检查 Skill adapter 不直接执行 Python/shell。
- 保存点：提交 Skill 复用闭环。

### P43-03 本地 Capability Pack fallback

- 在 `workflows/packs.py` 中实现只读本地 pack catalog。
- 新增仓库内置 pack manifest，组合已有 capability，不新增 executor。
- Kernel status/Web status 暴露 pack catalog。
- 保存点：提交 capability pack fallback。

### P43-04 Sandbox Posture 与风险复盘收敛

- 将 `recommended_posture`、`execution_backend` 和 policy trace 暴露到 Web workflow detail/pending view。
- 文档明确 approval/allowlist/scan 不是 sandbox。
- 保存点：提交 sandbox posture 与风险视图。

### P43-05 验证与收敛

- 更新验证脚本覆盖新增 files、skill、pack、posture。
- 跑完整验证命令。
- 保存点：提交最终验证与文档记录。

## 完成标准

- Plana 优先复用 AstrBot Skill/provider/Web/config 能力。
- 内部自建只保留 capability pack catalog、surface/toolset/policy 等 Plana 治理必需层。
- 每个大步骤有独立 git commit。
- 所有验证命令通过；`git diff --check` 仅允许既有 LF/CRLF warning。
