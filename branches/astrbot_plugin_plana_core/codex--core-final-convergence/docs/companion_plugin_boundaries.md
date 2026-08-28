# Companion Plugin Boundaries

本文记录 Plana 插件族的稳定职责拆分。Core 进入收口阶段后，新增能力应先判断属于哪个插件，避免 Core 继续膨胀。

图库保持独立资产服务；TTS 为独立实验轨，不进入当前发布套件。Workflow proposal runtime 已完全回收到 Core，独立 Workflow Center 已脱离运行时、配置和发布跟踪。

## 职责表

| 插件 | 负责 | 不负责 |
| --- | --- | --- |
| `astrbot_plugin_plana_core` | 对话路由、memory kernel、用户理解、workflow registry/compiler/executor、确认、审计、AstrBot 嵌入 Dashboard、受控 bridge handler | 外部 bot SDK、sidecar client、主动发送端点、图片二进制存储、TTS 后端 |
| `astrbot_plugin_plana_bridge_gateway` | 外部 HTTP 端点、外部 bot 节点适配、sidecar 转发、主动发送、proactive pickup、Codex Runner relay、未来 MCP 映射 | Core SQLite 写入、workflow 审批、最终业务授权、记忆策略 |
| `astrbot_plugin_plana_skill_center` | `SKILL.md` quarantine、scan、approval、export 和 integrity metadata | 安装/执行 skill、替 Core 做运行时授权 |
| `astrbot_plugin_plana_memory_warehouse` | Core-pushed raw episodic evidence、structured evidence、profile snapshots、daily maintenance summary、stable evidence ID、SQLite/FTS warehouse、后续大索引/备份/压缩 | Core prompt policy、画像/关系 mutation、workflow execution、自主采集策略 |
| `astrbot_plugin_plana_gallery` | 图片文件、sha256 去重、标签、caption、预览 Web、asset refs、后续 VLM/OCR | Core 记忆运行时、workflow 执行、Core Dashboard |
| `astrbot_plugin_plana_tts` | Core-facing voice synthesis API、TTS 来源和后端配置 | Core 记忆/workflow、bridge ingress、proactive delivery |

## 记忆仓库边界

Memory Warehouse 可以被动承接更多 Core 输出，但只能保存 evidence 和索引。它可以存 raw message、LLM response、structured memory extract、profile snapshot、daily maintenance summary 和未来附件元数据；它不能注册面向普通聊天的长期记忆写入工具，不能决定 prompt policy，也不能把 archive snippet 自行提升为画像、关系或长期事实。结构化 evidence 可以携带 `canonical_summary`、`persona_summary`、`summary_quality` 和 `promotable_to_profile`，这些字段只用于 Core 审计和后续回放，Warehouse 不据此写回 Core。

Core 与 Memory Warehouse 默认按同机安装处理：Core 只调用 `http://127.0.0.1:6185/api/plug/plana_warehouse` 的 Contract V1 HTTP API。网络、鉴权或插件不可用必须返回明确错误，不再直接导入 Warehouse Store；跨主机、反代或公网入口需要通过 Bridge/专用网关重做协议。

跨群对象复用由 Core 以 `actor_id` / `user_id` 归并。稳定的用户事实、偏好和昵称可以投影到 `global` profile；群内承诺、任务、临时上下文和局部关系保留在当前 scope。Warehouse API 支持 `scope_id`、`scope_ids`、`shared_scope_ids` 与 `actor_id` 组合检索，用于“当前群 + 共享群 + 同一对象”证据回放，但结果仍必须回到 Core 策略层处理。

## Core Contract

Core 对外只保留受控 bridge kind：

- `memory_query`
- `task_delegate`
- `result_report`
- `context_sync`
- `emotional_handoff`
- `workflow_request`

Gateway 将外部协议转换为这些 payload。Core 再决定请求是只读、pending、confirmed、rejected 还是 audited。`result_report`、`context_sync` 和 `emotional_handoff` 只进入 pending feedback，不能直接提升为长期记忆。

Codex Runner 委派使用 Core proactive 队列中的 `custom` payload，payload 内 `type=codex_delegate`。Core 只生成委派请求并记录 route trace；Bridge Gateway 只转发受控 payload；Runner 回传 summary、evidence、capability candidate 和 reuse fingerprint。Core 将候选隔离、校验并等待人工审批。

## 资产和语音边界

- Gallery 返回稳定 `asset_ref`，例如 `gallery:<sha-prefix>`。Core 不复制图片文件、不运行打标/索引 pipeline，也不把聊天反应图登记为 memory artifact；最近使用只保存稳定引用并用于冷却与重复排除。
- TTS 插件返回受控音频路径。Core 不保存外部 TTS URL、SoVITS 参数或后端选择。

Gallery 的聊天候选层属于 `semantic asset candidate`，只返回 `asset_ref`、caption、受控标签、逐图情绪 profile、matched emotions、score、分数拆解、review 和 safety 状态。Core 请求可包含最多两个受控情绪目标及各自强度、主次和权重；未升级客户端仍可只发送 facets。该层只负责提供可审计候选，不能决定发送。Core 在普通文字实际完成投递后执行稳定频率采样、候选请求和 hybrid 选择，再发送独立图片链；模型不能构造资产引用。FTS 和 caption match 只能生成候选，不能绕过 `needs-review`、`safety:safe`、路径校验、发送冷却或主情绪覆盖要求。

Core 与 Gallery 都不得持久化生产聊天原文用于候选反馈。Core 遥测只保存规范化情绪目标、候选引用和阶段结果；Gallery feedback 的兼容 `query` 字段保持为空。持久 persona PAD 只能作为弱先验影响情绪权重，不能直接触发发送。

TTS 响应可以扩展 `request_id`、`duration_ms`、`audio_bytes` 和 `format_verified`。Core 对旧响应保持兼容，但新后端必须明确空音频、格式不匹配、超时、路径越界和 TTL 清理策略。SoVITS 只属于 TTS 插件内部 engine，不进入 Core 配置或 Core executor。

## Workflow 和主动触发事件

Core workflow 可以维护只读 event ledger，用于 Dashboard、Bridge 回执和 Codex relay 进度展示。事件写入来源只允许 Core executor、Bridge result handler 或 Codex relay 状态回调；外部插件不得直接写 Core SQLite。

事件顺序约束：

- `progress`、`artifact`、`submitted` 等运行中事件必须早于 `completed`、`failed`、`cancelled` 等 terminal event。
- terminal event 只表达已有 run 的最终状态，不追加新权限。
- `/plana/api/workflows/events?run_id=<id>` 只能读取事件，不能触发执行。

Proactive task 可带 `trigger_reason`、`trigger_scene` 和 `effective_capability_view_hash`，用于解释“为何触发、在什么场景触发、看到的能力视图是什么”。这些字段不授予主动发送权限，也不改变 lease、retry、delivery boundary。

## Skill 和 Proposal 读取纪律

Core 内置 proposal runtime 负责 draft、短期 cache 和 recipe 筛选，不再调用外部 Workflow Center。Skill Center 导出的 SKILL.md 只作为 advisory recipe candidate；Core 只读取 manifest、正文必要片段和 manifest 声明的 reference，不扫描整个 reference 目录。

导出 manifest 可包含 `read_policy`、`reference_manifest` 和 `integrity_status`。Core 必须保持正文长度上限、hash drift guard 和 path containment guard；发现 drift 时只能降级或拒绝候选，不能继续读取正文。

## Bridge Channel Contract

Bridge Gateway 在进入 Core 前必须建立 normalized channel contract：

- 外部平台 session id 必须匿名化或稳定 hash，不能把原始账号 token 当作 Core actor。
- Gateway 负责 rate limit、capability downgrade、local/secret ingress 和 payload schema 收窄。
- human log 与 LLM sliding history 分离，模型上下文只拿必要片段。
- MCP discovery 只产生 canonical mapping，映射结果必须回到 Core 既有 bridge kind 与 capability registry。

## MCP 方向

未来 MCP support 放在 Bridge Gateway。MCP tool 应映射到标准 Core bridge payload、Gallery 读/搜 API 或其他附属插件的受控 API，不得直接拿 Core 数据库或 executor。

## 维护规则

- 新插件交互必须先说明是否属于 Core 内联能力。内联插件只能走本机回环并拒绝代理转发头；跨主机/公网入口只能放在 Bridge Gateway 或专用网关边界。
- 新 payload kind 或跨插件 contract 必须同步 Core、对应附属插件、README、`ARCHITECTURE.md` 和验证脚本。
- 未稳定的 Gallery 内部文档不作为 Core 收口阻塞项；TTS 与 Core 的调用契约必须保持本机回环和无内联 token/header。
