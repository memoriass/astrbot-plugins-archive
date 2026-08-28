# Plana Core 与附属插件综合审计

审计日期：2026-07-10

审计对象：`astrbot_plugin_plana_core` 当前工作区及 Bridge Gateway、Memory Warehouse、Workflow Center、Skill Center、Gallery、TTS；对照本地 `AstrBot`、`hermes-agent`、AngelHeart、Angel Memory、NachoBot、Cyrene-Agent，并采用 `C:\git\project_playbook` 的架构、验证和交付标准。

## 执行摘要

Plana 当前最强的部分不是陪聊表现，而是 AstrBot 插件形态下的治理中枢。Core 已具备 surface、toolset、capability registry、compiler、confirmation、approval drift、audit、workflow event、记忆质量门槛和附属插件边界。与 Hermes 相比，Plana 没有必要复制独立 gateway、任意终端执行、子代理平台和公共插件市场；AstrBot 已负责平台、provider、persona、skills、tool loop 和 Plugin Pages，Plana 保持策略中枢定位是正确方向。

当前主要问题是工程和产品两端不平衡：治理抽象扩张很快，但版本基线、端到端验证、用户可理解的说明能力、群聊参与质量、人格连续性和多模态陪伴闭环仍未达到同等成熟度。Core、Bridge、Workflow Center、Skill Center、Gallery 和 TTS 同时存在未提交改动，Memory Warehouse 没有 `.git` 目录，当前插件族不能形成可复现、可回滚、可发布的整体版本。

综合判断：

- 架构方向正确，执行治理边界优于多数陪聊项目。
- 工程成熟度处于 Beta 中期，尚不具备插件族整体发布条件。
- 陪伴体验弱于 AngelHeart、NachoBot 和 Cyrene-Agent。
- 记忆覆盖广，但冲突处理体验、共同回忆呈现和真实场景评测弱于 Angel Memory、NachoBot A_Memorix 和 Cyrene。
- 主动保持弱于 Hermes 是合理选择，但远程 Runner/broker 链路已接近第二套 agent runtime，必须及时收口。
- 最优策略是复用 AstrBot 的说明、persona、skill discovery、provider、tool schema、会话和 Plugin Pages；Plana 只增加受控 capability 解释、策略决策和审计。

## 审计基线

### 工作区状态

| 仓库 | 分支 | 未提交项 | 结论 |
| --- | --- | ---: | --- |
| Core | `codex/plana-secretary-full-rollout` | 82 | 大规模开发中，不能作为发布基线 |
| Bridge Gateway | `codex/bridge-gallery-split` | 14 | Hermes relay 与 proactive 链路未收口 |
| Workflow Center | `codex/workflow-center-contract-guard` | 7 | Contract guard 正在迭代 |
| Skill Center | `codex/plana-skill-center-hermes` | 9 | integrity/governance 正在迭代 |
| Gallery | `codex/bridge-gallery-split` | 15 | 目录迁移中，包含删除和未跟踪文件 |
| TTS | `main` | 8 | 直接在主分支开发，不符合 playbook |
| Memory Warehouse | 无 Git 仓库 | 不适用 | 无法提交、回滚和标记版本 |

以上是当前最高优先级风险。本文评价的是工作区能力，不代表已发布能力。

### 201/202 联通整改实测

本次审计同时完成了生产 AstrBot 与轻量 Hermes 执行端的真实联调，测试结果按证据层级区分如下：

| 层级 | 已验证结果 | 未证明内容 |
| --- | --- | --- |
| 静态检查 | native tool 路由、Hermes lane 判定、Runner adapter、Bridge result handler 和失败边界专项脚本通过 | 不能替代真实 ChatUI 与远端服务 |
| 远端服务 | 201 AstrBot active；202 `/health` 返回 `executes_tasks=true`；interactive worker 为 1；long/high-isolation/import 为 0；目录、虚拟环境、120 秒超时和 768 MiB systemd 内存上限生效 | 上游模型 provider 的持续稳定性 |
| ChatUI/Open API | 网络探测一次请求完成；公共小文件下载并回传 artifact；明确 Hermes 短请求已真实成功过；真实超时会写入 failed 并主动回传恢复建议；通用基础任务未进入 Workflow Center | 大型构建、批量抓取、浏览器自动化和长时间后台任务 |

运行边界：

- 201 为 `192.168.1.201`，约 3.8 GiB 内存；202 为 `192.168.1.202`，约 916 MiB 内存和 2 GiB Swap。
- 202 已迁移到 `/home/ubuntu/hermes/{agent,runner,data}`；`/opt` 原目录和 `/root/plana-hermes-backup-20260710-143501` 保留回退。
- Hermes 真实入口为虚拟环境内 `.venv/bin/hermes chat --query ...`，不再返回固定 stub；Runner SQLite、任务、结果和 artifact 位于 `/home/ubuntu/hermes/data/runner`。
- 零 worker lane 在入队前返回 `409 lane_disabled`，实测 long 队列前后均为 0，避免周六前的大任务永久排队。
- 201 的 Dashboard `/api/plug/*` 要求 JWT，202 直连 callback 会返回 401；当前显式关闭 callback，Bridge 使用覆盖 120 秒超时窗口的内网轮询。真实 15 秒测试超时已完成 `submitted -> failed -> ChatUI 主动失败通知`，测试后恢复 120 秒。
- 真实成功结果重放验证了 Core 落库后的主动发送：ChatUI 收到 `ok` 摘要和 artifact 名称/大小。该重放只验证发送链，不能替代新一次模型成功；联调期间上游 provider 曾连续 120 秒超时，属于当前 P0 稳定性风险。
- AstrBot 原生 Tool Loop 已实际完成百度 443 TCP 探测和公共 URL 小文件下载；仍观察到模型第一次网络工具调用缺少参数、自动重试和重复前置话术，属于延迟与交互质量缺陷，不是 Workflow Center 截断。
- 通用 shell 路由曾因命令解析失败被错误委派 Hermes，随后修复为：支持中文全角冒号与“shell 执行”表达、local command 不因 capability 暂不可用而远程升级、使用受控 JSON draft 固定加入 `command.run_confirmed`。201 显式启用 `secretary_allow_local_command_execution=true` 后，真实 ChatUI 结果为 `waiting_confirm`，未执行命令；危险删除请求仍被拒绝。

### 整改优先级

- **P0 已完成：** 202 目录迁移、Hermes 虚拟环境、真实 CLI adapter、`executes_tasks=true`、201→202 委派、准确失败终态、零 worker lane 快速失败、Core 持久化后的主动通知、native mode 显式配置。
- **P0 待完成：** 稳定 Hermes 上游 provider；冻结可发布 commit/manifest；确认周六高资源迁移或扩容后的大型任务基线。
- **P1：** 统一 `TaskEnvelope`、实现 `/plana why`、把 202 artifact 安全回传或复制到 AstrBot artifact、增加 callback 鉴权专用入口与轮询恢复、补 Runner/AstrBot 重启恢复测试。
- **P2：** 群聊参与评测、记忆解释与修正、多模态陪伴闭环，以及 AngelHeart/NachoBot/Cyrene 风格的体验指标。

### 规模信号

Core 当前约 176 个 Python/JavaScript 文件、3.3 万行代码；六个附属插件另有约 1.1 万行代码。Core 单文件均控制在 500 行内，但多个文件位于 480-500 行。行数门槛已经执行，不能把“低于 500 行”当成模块低耦合的证明。

## Core 优势

1. **执行权边界清晰。** Workflow Center 只输出 proposal，Core 重新 compile；Skill Center 只 quarantine、scan、approve、export；Bridge 只做协议适配和 relay；Warehouse 只保存 evidence。
2. **默认拒绝优于能力优先。** surface、toolset、capability allow/deny、risk、confirmation source、proposal hash 和 capability view hash 共同限制执行路径。
3. **记忆不是单一向量库。** 已覆盖 episodic、semantic、profile、relation、concept、memory atom、feedback、recall gap、quality、decay、maintenance 和 Warehouse evidence。
4. **错误路径较明确。** Warehouse 不可用不会伪装成无结果；远程 Runner 失败进入重试或失败状态。
5. **运维视图较完整。** Dashboard 已展示 workflow、route trace、remote task、memory production、maintenance 和 companion status。
6. **入口基本受控。** `main.py` 主要负责装配和 AstrBot hook，业务逻辑已下沉。

## 主要发现

### P0：发布与版本完整性

插件族没有统一、可复现的版本基线。多个仓库同时存在大量未提交改动，不同插件位于不同 feature branch，TTS 在 `main` 上直接开发，Warehouse 没有 Git 元数据。Core README 的验证命令跨多个 sibling 目录，但没有 manifest 固定 companion commit、contract version 和兼容范围。

影响：

- 无法证明某次 Core 验证使用的是哪一版 companion。
- 无法对线上问题执行准确回退。
- Contract 测试通过可能只是当前本机目录偶然匹配。
- 发布包、生产目录和开发目录容易漂移。

建议：

- 立即把 Memory Warehouse 纳入独立 Git 仓库。
- TTS 迁移到 `codex/<topic>` 分支。
- 增加插件族 `compatibility-manifest.json`，记录 plugin id、version、contract version、兼容范围和已验证 commit。
- 建立一次冻结基线，各仓库分别提交后只修集成问题。

### P1：编排层数量过多

一个自然语言任务可能经过 wake state、entry filter、local analyzer、LLM preflight、DialogueRouter、AssistantTaskRouter/Broker、TaskSession、execution intent、execution routing、Workflow Center proposal、Core compiler、confirmation、proactive queue、Bridge relay、Hermes Runner 和 result report。各层都保存 reason 或状态，但缺少正式端到端状态机和唯一决策所有者。

影响：

- 同一意图可能被多次分类并产生不一致结论。
- 本地任务、workflow、remote task、proactive task 概念重叠。
- 失败、取消、确认和重试终态可能在多个 store 漂移。
- 新维护者难以判断在哪一层增加能力。

建议：

- 统一为 `TaskEnvelope`：`turn_id`、`task_id`、`scope_id`、`actor_id`、`intent`、`route`、`risk`、`execution_target`、`status`。
- 只允许一个组件拥有最终 route 决策，其他组件只能提供 hint 或 policy veto。
- 把本地 workflow 和 remote runner 视为 execution backend，不再发展独立任务语义。
- 固定终态：`answered`、`rejected`、`pending_confirmation`、`running_local`、`queued_remote`、`completed`、`failed`、`cancelled`。

### P1：依赖 AstrBot 私有实现

Core 直接导入或操作 `astrbot.core.skills.skill_manager.SkillManager`、session manager、`ProviderRequest` 内部字段和 `ToolSet` 多个方法。`dialogue/tool_policy.py` 通过替换 provider schema、`get_func` 等方法隐藏工具，并用正则删除 AstrBot 生成的 skills、computer use 和 workspace prompt。

影响：

- AstrBot 升级时容易静默失效。
- Core 绕过 AstrBot persona/tool/skill 选择链，形成第二套策略。
- 正则删 prompt 可能误删或无法匹配新版本格式。
- monkey patch ToolSet 会产生难定位的 provider/tool loop 差异。

建议：

- 优先复用或向 AstrBot补充公开的按请求过滤 toolset、读取当前 persona skills、构建只读 skill inventory 接口。
- 暂时无法公开化的兼容代码集中到单一 `astr_compat/` 适配层，并绑定 AstrBot commit/version 测试。
- 不再正则删除整段 Skills prompt，改为让 persona 只启用 Plana 允许的说明型 skills。
- 不再修改 ToolSet 实例方法，改为构造新 ToolSet 或使用框架的 plugin/session tool filter。

### P1：验证以静态契约为主

Core 的 check 脚本覆盖文件存在、文档、配置、schema、路由和部分 fake runtime 行为，这是优势。但大量检查仍依赖源码字符串、fake event、fake provider 和同进程对象，不能证明真实 AstrBot 生命周期、Plugin Pages 鉴权、跨插件 HTTP、重启恢复、数据库迁移和并发确认正确。

缺少的关键测试：

- 真实 AstrBot 启动后的插件发现、加载、卸载和重载。
- Core + Warehouse + Workflow Center + Skill Center 的真实 loopback contract。
- Dashboard bridge SDK 下的 GET/POST、401、asset token 和别名路由。
- 两个用户或群同时确认、取消任务时的隔离。
- Core/Bridge 中途重启后的 proactive/remote task 恢复。
- Warehouse unavailable、Center timeout、Skill hash drift 的故障注入。
- AstrBot 升级后的 tool filtering 和 skills prompt 兼容性。

建议保留现有快速 check，新增启动本地 AstrBot 实例的 `integration_live`；为 companion 提供统一 health/contract fixture；增加空库、上一发布版数据库和中断迁移 fixture。

### P1：说明能力尚未产品化

Core 内部保存大量 route reason、risk reason、policy notes、memory source 和 maintenance error，但主要出现在 Dashboard 或开发状态。普通用户缺少稳定入口询问：

- 为什么回复或没有回复。
- 为什么本地执行、要求确认或委派 Hermes。
- 使用了哪些记忆，哪些因质量低未采用。
- 当前会做什么、不会做什么、需要安装哪个插件。
- skill 是说明型 recipe 还是可执行 capability。

建议新增只读 `ExplanationService`，只消费已有 trace，不再次调用 planner，也不改变执行结果：

- `/plana why`：解释上一轮 route、wake、preflight 和执行目标。
- `/plana capability <需求>`：结合 AstrBot skill description、Core registry 和 companion status 说明可用路径。
- `/plana memory-trace`：返回采用、降权、拒绝和缺失的记忆来源摘要。
- Dashboard 统一展示 `decision_summary`，避免普通用户阅读 hash 和原始 policy JSON。

说明内容必须区分“框架能力说明”“Plana 治理许可”“当前环境可用性”和“本轮实际使用”。不得暴露 chain-of-thought、完整模型 reasoning、内部 prompt、密钥或隐藏 capability。

### P2：群聊参与模型弱于 AngelHeart

Core 已有 wake、summoned、familiar、observation 和 LLM preflight，但仍偏向路由门控。AngelHeart 把群聊参与当成独立产品问题：轻量分析模型、话题/实体/事实/关键词提取、四状态转换、事件扣押、等待反馈和决策注入主模型。

Plana 不应照搬全部实现，但应补充群聊参与评分、连续话题和关系影响、冷却和打断成本、多人对象判断，以及“决定不回复”的离线评估集。这部分应留在 `dialogue/`，不属于 Workflow Center。

### P2：记忆覆盖广，但体验闭环不够强

与 Angel Memory、A_Memorix 和 Cyrene 相比，Plana 的数据类型和治理字段不弱；不足主要在效果证明：

- 缺少用户可见的共同回忆呈现。
- 缺少旧偏好与新偏好冲突的自然语言修正流程。
- 缺少真实对话集上的 recall precision、错误注入率和 profile drift 指标。
- memory quality 尚未形成可回放评测集。
- Core/Warehouse 双存储的保留期、删除传播和数据主体请求缺少正式协议。

优先建立 100-300 条多轮记忆评测集，覆盖同名人物、跨群用户、偏好变化、否定、玩笑、引用和第三人称。指标至少包括 recall hit、wrong-user leak、wrong-scope leak、stale fact、unsupported profile promotion 和 prompt budget。

### P2：Core 仍有膨胀趋势

Core 已同时拥有 dialogue、memory、identity、relation、persona、task、workflow、proactive、bridge contract、web、jobs 和远程任务 store。建议坚持：

- 对话参与、上下文和解释：Core。
- 记忆策略、画像提升、关系和 prompt budget：Core。
- proposal 实验和多模型 planning：Workflow Center。
- 原始证据、大索引、备份恢复：Warehouse。
- 外部通道、主动发送、Runner/MCP adapter：Bridge。
- Skill 草案治理：Skill Center。
- 表情、图片、caption、OCR/VLM：Gallery。
- ASR/TTS/音频生命周期：语音插件，不进入 Core。

## 附属插件评审

### Bridge Gateway

优点：同进程 Core adapter、relay-only Hermes、LAN URL policy、proactive 自动领取和结果回流边界清楚。

不足：同时承担 bridge、主动发送、Nacho 适配、Hermes relay 和未来 MCP，职责开始变宽；LAN 位置不应是唯一 Runner 身份；relay、callback、retry 需要幂等键和重复回调测试。建议继续拆分 channel adapter、delivery、runner relay；MCP discovery 只能产生 capability candidate。

### Memory Warehouse

优点：evidence-only、稳定 ID、FTS、bounded snippet、跨 scope/actor 查询和 loopback 边界合理。

不足：无 Git 仓库是阻断级问题；尚未证明容量、备份、恢复和删除传播；Core 本地 fallback 直接访问 Warehouse Store 会形成模块耦合。建议先版本化并完成恢复演练、删除/保留期协议和百万级 evidence 基准，再扩展 embedding 或附件。

### Workflow Center

优点：proposal-only、Contract V3、capability hash echo、cache 不保存执行状态，边界正确。

不足：如果 planner/specialist/critic 没有显著提高 proposal 成功率，它只是增加网络和模型调用；与 Core 本地 advisor 并存会形成两套 proposal 行为。应建立 benchmark；如果没有显著收益，按既有决策回收为 Core 内部模块。

### Skill Center

优点：quarantine、scan、approval、integrity hash、export manifest 和禁止自动执行符合供应链治理经验。

不足：用户难以理解 Skill Center 与 AstrBot 原生 Skills 的关系；静态 executable hint 不能代替 capability mapping。产品语言应固定为“技能说明与流程配方治理”：AstrBot Skill 负责说明发现，Core capability 负责执行授权，Skill Center 负责草案审核。

### Gallery

优点：稳定 `asset_ref`、sha256 去重、needs-review、标签工作台和公网发布隔离接近可用产品。

不足：目录重构尚未形成基线；缺少“对话情绪/场景 -> 表情候选 -> 反馈学习”闭环；远端 URL 失效、删除、内容审核和迁移未闭环。建议 Core 只传受控 scene/emotion/tag hint，Gallery 返回候选和原因，最终发送由 Bridge/AstrBot 完成。

### TTS

优点：request id、duration、audio bytes、format verification、TTL cleanup 和 backend 隔离方向正确。

不足：在 `main` 直接开发；只覆盖合成，未覆盖 ASR、打断、流式播放、语音轮次和情感参数治理。TTS 应保持小插件；语音通话应另建 voice runtime，不把长连接状态机塞回 Core。

## 对标差距矩阵

| 能力域 | Plana | Hermes | Angel 系列 | NachoBot | Cyrene | 判断 |
| --- | --- | --- | --- | --- | --- | --- |
| 执行治理 | 强 | 强且执行面更广 | 弱 | 中 | 中 | 保持当前方向 |
| 平台接入 | 复用 AstrBot | 自建 gateway | 复用 AstrBot | 多 adapter | 桌面+飞书/微信 | 不复制 gateway |
| 群聊参与 | 中 | 非重点 | 强 | 强 | 弱 | 借鉴 AngelHeart/Nacho |
| 长期记忆 | 强 | provider 化 | 强 | 强 | 强 | 建评测，不堆类型 |
| 人格情绪 | 弱到中 | 中 | 强 | 强 | 很强 | 主要产品短板 |
| 主动陪伴 | 治理强、场景弱 | cron/agent 强 | 有主动消息 | 强 | 场景评分强 | 补场景层 |
| 多模态表达 | companion 未闭环 | 工具化 | 部分 | 强 | 很强 | 通过 companion 补齐 |
| Skill 生态 | 治理强、执行保守 | 自进化可执行 | 非重点 | 插件化 | 本地 skills | 不复制自动执行 |
| 说明能力 | 后台数据强、用户说明弱 | CLI/TUI 丰富 | 决策日志强 | reasoning/动作链丰富 | memory trace 强 | 新增 ExplanationService |
| 测试发布 | check 多、集成不足 | 测试规模大 | 各自测试 | 工程债高 | 单测较多 | 增加真实 Astr 集成 |

## AstrBot 可复用能力

### 应直接复用

1. **Persona。** AstrBot 负责最终人格 system prompt、persona tools 和 persona skills；Core 只注入有界记忆、关系、模式和策略提醒。
2. **Skills progressive disclosure。** AstrBot 已展示 skill 名称、description、路径和触发规则。Plana 应复用这套能力说明，不再生成第二份普通聊天 skill prompt。
3. **Provider。** Core 只按 role 选择 AstrBot provider，不维护独立 provider SDK。
4. **Tool schema 和会话过滤。** 使用公共 tool manager、persona toolset 和 session plugin filter，不 monkey patch ToolSet。
5. **Plugin Pages。** 管理页继续走 AstrBot bridge SDK 和认证上下文。
6. **多模态预处理。** 图片 caption、引用消息、音频附件和平台差异优先交给 AstrBot。
7. **会话启停。** Core 遵守 AstrBot session service/plugin manager，不建立平行启停体系。

### Plana 应保留的增量

- 将 AstrBot skill description 映射为只读 recipe candidate。
- 将 persona、skill、tool 和 companion availability 汇总成 capability explanation。
- 对副作用再经过 Core registry、risk policy 和 confirmation。
- 对记忆、route、workflow 和 remote execution 提供审计 trace。

### 不应直接开放

- 不把 AstrBot Skills 的 shell/文件说明变成 Core executor 权限。
- 不让 MCP 或 Computer Use discovery 自动扩大 registry。
- 不让 persona tools 绕过写操作确认。
- 不长期维护 prompt 正则和 ToolSet monkey patch。

## 建议的说明能力

```text
AstrBot persona/skills/tools inventory
            +
Core capability registry and policy
            +
Companion health/contract status
            +
Last-turn route, memory and workflow trace
            ↓
      ExplanationService (read-only)
            ↓
chat explanation / Dashboard summary / diagnostics API
```

输出固定为四层：需求识别、可用能力、治理结果、证据与限制。

## 分阶段路线图

### P0：冻结与可发布基线

- Warehouse 初始化为 Git 仓库。
- companion 在稳定 feature branch 提交，停止在 `main` 直接开发。
- 新增生态兼容 manifest。
- 完成全插件族安装、启动、重启和回滚演练。

完成标准：同一 manifest 可在干净目录重建全部插件并通过现有 check。

### P1：统一任务与解释模型

- 定义单一 `TaskEnvelope` 和终态。
- 收敛 Dialogue、Task Broker、Workflow 和 Remote Runner 的 route 所有权。
- 新增 ExplanationService、`/plana why` 和 capability explanation。
- 私有依赖集中到 compat adapter，移除 ToolSet monkey patch。

完成标准：任意任务可用一个 task id 查询完整 route、policy、confirmation、backend 和终态。

### P1：真实 AstrBot 集成验证

- 启动测试 AstrBot 并安装 Core/companions。
- 测试 Plugin Pages、真实 provider request、tool filtering、persona skills 和 loopback API。
- 测试重启恢复、并发确认、故障注入和数据库迁移。

完成标准：不依赖源码字符串即可验证主要 contract。

### P2：群聊参与质量

- 建立 AngelHeart 风格离线群聊参与数据集。
- 增加参与评分、多人对象判断、冷却和连续话题特征。
- 保留本地 fallback，模型只做受控 `respond/action` 分类。

完成标准：误插话率、漏回复率和额外 LLM 成本有量化数据。

### P2：记忆效果评测

- 建立跨群、偏好变化、冲突、否定和第三人称记忆集。
- 暴露用户可理解的 memory trace 和修正流程。
- 验证 Warehouse 删除传播、保留期、备份恢复和规模索引。

完成标准：记忆质量用数据证明，不再以模块数量证明。

### P3：陪伴与多模态闭环

- Core 输出受控 scene/emotion hints。
- Gallery 负责表情/图片候选、review 和反馈。
- TTS/voice runtime 负责情感语音、打断和音频状态。
- Bridge/AstrBot 负责最终发送和平台适配。

完成标准：体验提升不扩大 Core 的文件、网络或执行权限。

## 不建议继续投入

- 在 Core 复制 Hermes 完整 agent loop、subagent、terminal backend 或 plugin market。
- 在 Workflow Center 增加执行器。
- 在 Warehouse 增加画像提升或自主记忆判定。
- 在 Skill Center 自动安装、启用或执行 skill。
- 在 Bridge 直接注册未知 MCP 工具为 Core capability。
- 在没有真实评测前继续增加 memory kind、route 层或 advisor role。

## 2026-07-12 双机链路实测补充

本轮以“先跑通、后优化网络与响应速度”为验收原则。模型首响应延迟、偶发上游 500 和单次超时单独记录，不作为阻断任务治理、取消、产物传输和结果回流实现的理由。

### 已完成的真实验证

- 202 Runner `/health` 返回 `executes_tasks=true`，`interactive` 与 `long` lane 均有真实 worker。
- 201 Core 经 Bridge 将短任务委派到 202，Hermes 返回真实模型文本，Core 记录成功终态，AstrBot 主动消息进入消息历史。
- 运行中任务可通过 Runner cancel API 终止整个进程组，终态为 `cancelled`，无遗留 Hermes 子进程。
- Runner 为结果清单中的产物提供受 LAN allowlist 和现有 Bearer token 保护的下载端点；请求不能使用任意文件路径，只能使用 `run_id + artifact_id`。
- Bridge 将产物下载到 201 的 AstrBot 插件数据目录，限制单文件最大 100 MiB，并同时校验声明字节数和 SHA-256；校验失败时删除不完整文件。
- 使用此前 Hermes 真实生成的四个产物完成回放验证：stdout 文本、`summary.md`、`risks.md` 和 `checklist.md` 均从 202 下载到 201，大小与 SHA-256 完全一致。
- Bridge 已构造 AstrBot `File` 或本地图片消息段；平台发送失败时本地 artifact 保留，不把 202 绝对路径作为用户可用产物。
- callback 与 polling 统一经过 `prepare_result`，并按 `runner_run_id` 去重通知，避免双通道重复发送。

### 当前非阻塞问题

- 一个直接 long 任务在模型首响应阶段达到 180 秒超时；同类任务此前也存在 20 秒左右成功记录，判断为 provider/网络抖动而非 Runner 队列或内存问题。
- 202 扩容后未观察到 OOM，功能链路测试继续推进；响应速度、provider 重试和网络质量放到后续专项优化。
- AstrBot WebUI 的插件 HTTP 路由受统一面板鉴权保护，Runner callback 需要进一步明确机器到机器鉴权入口；当前生产结果回流继续使用已验证的 Bridge polling，不影响链路运行。
- 真实 ChatUI/群聊文件发送和自然语言取消仍需使用有效用户会话完成最终体验验收；静态检查或数据库回放不能替代该项。

### 阶段结论

截至本轮，任务委派、真实 Hermes 执行、状态轮询、取消、结果持久化、主动通知和跨机 artifact 取回已形成可运行闭环。后续优先补真实 ChatUI 文件发送与群聊取消，再处理 provider 延迟、callback 鉴权和大型任务性能，不再回到 Core 内建设第二套通用 Agent Loop。

## 最终结论

Plana 的竞争力应定义为“依托 AstrBot 的可治理秘书与陪伴中枢”，而不是“小型 Hermes”或把 NachoBot/Cyrene 全部塞进一个插件。

Plana 已在执行治理、确认、审计、插件边界和记忆数据模型上形成优势；真正不足的是发布纪律、AstrBot 公共接口复用、任务状态统一、真实集成验证、用户可理解的说明能力，以及人格、群聊参与和多模态陪伴的可感知效果。

下一阶段最有价值的工作不是扩充 capability 数量，而是冻结版本、跑通真实生态集成、移除私有 monkey patch、统一任务状态，并把现有 trace 转化为用户能够理解的说明。完成这些之后，再借鉴 AngelHeart 的参与决策、Angel Memory/NachoBot/Cyrene 的记忆与陪伴方法补产品体验，Plana 才会从“架构完整的 Beta”进入“可长期维护的 AstrBot 原生秘书系统”。
