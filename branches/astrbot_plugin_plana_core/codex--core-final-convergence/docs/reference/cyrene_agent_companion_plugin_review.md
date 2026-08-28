# Cyrene-Agent Companion Plugin Review

本文归档对 `C:\git\Cyrene-Agent` 的只读分析结论，用于指导 Plana Core 与附属插件后续优化。结论只吸收工程机制，不复制 Cyrene 的桌面 Agent、Live2D、键鼠控制、ASR/TTS 主循环或宿主侧自动操作能力。

## 总体原则

- Core 继续作为唯一策略、确认、执行和审计边界。
- 附属插件只能提供 proposal、evidence、candidate、asset、voice 或 delivery relay。
- 外部工具发现、语义检索、主动触发和长任务执行都必须回到 Core 已登记 capability、确认 gate 和审计路径。
- LLM 与 semantic retrieval 只作为 advisory layer，不能直接扩大执行权限。

## 可借鉴机制

### 记忆与聊天

Cyrene 将 prompt 构建、记忆注入和运行后副作用分离；长期记忆写入要求证据、归因和明确用户边界。Plana 可借鉴的是“注入内容可追踪、纠错能回到证据”的机制，而不是复制其人格世界观或全局桌面状态。

Plana 落点：

- Memory Warehouse 继续只保存 evidence 与索引。
- Core 后续可记录 prompt 注入来源与用户纠错反馈，用于 replay 和冲突处理。
- 画像、关系和长期事实仍由 Core 策略层决定是否提升。

### Skill 与引用读取

Cyrene 的 skill 机制使用目录名作为稳定 id，正文懒读取，reference 由 manifest 控制，并带路径逃逸和每轮去重限制。Plana Skill Center 应导出同类读取纪律，但 Core 只读取候选摘要、manifest 与必要片段。

Plana 落点：

- exported skill 增加 `read_policy`、`reference_manifest`、`integrity_status`。
- Core 继续将 SKILL.md 视为 recipe candidate，不注册 executor。
- reference 只能从 manifest 声明中按需读取，禁止一次性吞整个 reference 目录。

### Bridge、MCP 与外部通道

Cyrene 将外部通道归一化为 Incoming/Outgoing contract，并在通道层声明 capability、rate limit 和会话身份。MCP tool 需要先映射为安全 id 和风险等级。

Plana 落点：

- MCP discovery 只属于 Bridge Gateway。
- Gateway 做 canonical mapping、匿名 session id、rate limit 和 capability downgrade。
- 映射后的请求必须回到 Core bridge payload kind、capability registry、confirmation gate 和 audit。
- human log 与 LLM sliding history 分开保存，避免把完整外部日志直接塞进模型上下文。

### Workflow 与长任务

Cyrene 对长任务有运行 guard、进度事件和 terminal event 顺序要求：side effect、artifact、progress 必须先于完成/失败事件。Plana 应将这个要求沉淀为 workflow event ledger，而不是把长任务执行搬进 Core。

Plana 落点：

- Core workflow run 增加只读事件账本。
- Core executor、Bridge result handler、Hermes relay 状态回调可写 progress、artifact、submitted、result、failure 事件。
- completed/failed/cancelled 等 terminal event 必须排在 progress/artifact 后面。
- Dashboard 使用同一事件序列展示长任务进度。

### 主动触发

Cyrene 的 opener 使用场景评分、冷却、概率 gate、点击/忽略反馈。Plana 第一阶段只吸收解释字段，不改变已有 lease/retry 队列。

Plana 落点：

- proactive task 增加 `trigger_reason`、`trigger_scene`、`effective_capability_view_hash`。
- 字段仅用于解释和诊断，不授予新执行权限。
- 场景评分、cooldown 和反馈学习后续在不破坏队列语义的前提下迭代。

### Gallery 与素材检索

Cyrene 的 sticker 检索可以用 embedding 生成候选，但生产发送仍需本地路径 guard 与受控选择。Plana Gallery 可加入 semantic candidate layer，但只能进入 review/candidate path。

Plana 落点：

- semantic candidate 返回 `asset_ref`、score、matched tags、review status。
- `needs-review` 资产不能绕过生产发送规则。
- tagging workbench 可使用 embedding 辅助，但最终标签仍由受控更新接口写入。

### TTS

Cyrene TTS 对 request id、timeout、content type、错误预览和音频字节数做统一处理。Plana TTS 可补齐 metadata 与音频生命周期治理。

Plana 落点：

- synthesis response 返回 `request_id`、`duration_ms`、`audio_bytes`、`format_verified`。
- 空音频、格式不匹配、超时和路径越界必须有明确错误。
- 音频文件按 TTL 清理，SoVITS 后端只作为 TTS 插件内部后端，不进入 Core。

## 禁止照搬项

- 不复制桌面 Agent 主循环、键鼠控制、窗口操作、屏幕读取或本机任意工具执行。
- 不把 MCP discovery 直接接入 Core executor。
- 不让 Skill Center 导出的 SKILL.md 自动安装、自动执行或注册 side-effect 工具。
- 不让 Gallery semantic match 直接选中 `needs-review` 素材用于生产发送。
- 不把外部通道的完整历史直接作为 Core prompt history。

## 优先级

1. 归档本文件并同步 companion boundary。
2. 增加 Skill/TTS/Gallery/Proactive 的低风险治理字段。
3. 增加 workflow event ledger 与只读 API。
4. 再迭代主动触发评分、cooldown 和反馈学习。
5. MCP 只在 Bridge Gateway 后续扩展，并保持 Core authority 不外扩。
