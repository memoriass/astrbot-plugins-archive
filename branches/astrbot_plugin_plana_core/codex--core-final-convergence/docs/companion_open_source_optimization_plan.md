# Plana 附属插件开源项目优化计划

本文把开源项目对标转换为 Plana 插件族可执行的改造清单。目标不是把其他 Agent 框架整体并入 Plana，而是在不扩大 Core 权限、不建立第二套 AstrBot runtime 的前提下，复用已经验证过的工程机制。

## 结论

存在可用于优化 Plana 附属插件的开源项目，但应按“借机制、不搬平台”的原则使用：

- AstrBot 是宿主能力的第一复用来源，优先复用 persona、provider、skills、tool schema、会话过滤、Plugin Pages 和多模态预处理。
- Hermes Agent 只适合作为隔离长任务 Runner 和任务事件模型的参考，不进入 Core 主对话循环。
- Cyrene-Agent 适合参考记忆证据链、受控 skill/reference 读取、场景触发解释、素材候选和音频响应治理。
- AngelHeart、Angel Memory 与 NachoBot 适合参考群聊参与、关系连续性、记忆激活和陪伴反馈，不复制其人格设定或宿主耦合。
- Mem0、Letta/MemGPT 类项目适合用于设计记忆评测、冲突处理和可追踪注入实验，不直接替换 Core 与 Warehouse 的数据边界。
- Pipecat 类语音框架适合未来独立 Voice Runtime 的流式 ASR/TTS、打断和轮次状态机，不应塞入现有 TTS 小插件或 Core。

## 强制边界

任何开源机制进入 Plana 前都必须满足：

1. LLM、embedding、MCP discovery 和语义检索只返回 candidate、proposal、evidence 或 explanation。
2. 写入、删除、批量变更、账号状态变化和主动发送仍经过 Core capability、policy、confirmation 和 audit。
3. 附属插件不直接访问 Core SQLite，不注册绕过 Core 的副作用 executor。
4. AstrBot 已有稳定能力时不建立平行 provider、persona、session、tool loop、Plugin Pages 或平台 gateway。
5. 引入第三方代码前单独检查许可证、依赖体积、维护活跃度、数据外发路径和升级成本。

## 插件映射

### Bridge Gateway

可参考：Hermes 的任务事件和隔离执行边界、Cyrene 的 channel contract、AstrBot 的平台适配。

优先改造：

- 把 channel adapter、delivery relay、runner relay 分成独立模块，Gateway 入口只做协议归一化和装配。
- 为提交、轮询、回调和主动回传统一 `idempotency_key`，增加重复提交、重复终态和乱序事件测试。
- Runner 身份从“LAN 地址可信”升级为稳定 runner id、声明能力、lane 和可轮换认证材料；LAN policy 只作为网络层限制。
- MCP discovery 只生成 canonical capability candidate，不能直接产生 Core executor。

不引入：Hermes 完整 gateway、任意终端工具、公共插件市场或自主 subagent loop。

### Memory Warehouse

可参考：Mem0/Letta 的记忆评测与冲突场景、Cyrene 的证据归因、Angel Memory/NachoBot 的激活与关系连续性。

优先改造：

- 先建立独立 Git 基线、版本号、迁移记录、备份和恢复脚本；未完成前不扩展 embedding。
- 建立固定评测集：同名冲突、跨群 scope、昵称变化、事实更正、过期偏好、错误说话人、删除传播和召回空结果。
- 为每条检索结果保留 evidence id、scope、actor、时间、来源和裁剪原因，Core 注入时记录使用了哪些 evidence。
- 增加容量基准和恢复演练，至少覆盖空库、上一版本数据库、百万级 evidence 和中断迁移。
- 移除 Core 对 Warehouse Store 的直接 fallback，统一经过 loopback client/contract fixture。

不引入：第三方记忆框架的自动写入策略、全局共享记忆或绕过 Core 的画像提升逻辑。

### Workflow Center

可参考：Hermes 的 planner/critic 思路，但必须用 benchmark 决定是否保留远端中心。

优先改造：

- 建立 proposal benchmark，比较 Core 本地 advisor、远端 planner 和规则 fallback 的成功率、延迟、token 成本及无效步骤率。
- 固定 proposal-only contract；Center 只返回 capability id、参数草案、风险提示、依据和 contract hash。
- 若远端方案没有显著优于本地 advisor，将其回收为 Core 内部可选模块，避免长期维护两套规划行为。
- 为 contract drift、未知 capability、过期 hash、超时和空 proposal 建立统一 fixture。

不引入：远端直接执行、自动确认、动态工具注册或由模型发明 workflow 名称。

### Skill Center

可参考：AstrBot Skills 的渐进披露、Cyrene 的 manifest/reference 读取纪律和常见软件供应链隔离流程。

优先改造：

- 产品名称固定为“技能说明与流程配方治理”，明确其不替代 AstrBot Skills。
- 导出 manifest 必须包含稳定 id、内容 hash、`read_policy`、`reference_manifest`、`integrity_status` 和来源信息。
- Core 只读取候选摘要、SKILL.md 必要片段和 manifest 声明的 reference；单轮读取去重并限制总字节数。
- executable hint 只能帮助映射已有 capability，不能创建 executor。
- 增加路径逃逸、符号链接、hash drift、超大正文、嵌套 reference 和恶意指令测试。

不引入：自动安装、自动更新、自动执行、公共远程市场和未经审核的脚本入口。

### Gallery

可参考：Cyrene 的 sticker candidate、CLIP/open-clip 类语义候选和成熟图库的内容寻址模式。

优先改造：

- 增加只读 semantic candidate 层，返回 `asset_ref`、score、matched tags、review status 和候选原因。
- Core 只传受控 scene/emotion/tag hint；Gallery 不接收完整 prompt，也不决定最终发送。
- 建立远端 URL 失效、内容删除、hash 重复、标签迁移、审核撤回和引用悬空测试。
- 收集“采用、跳过、替换、负反馈”事件，用于调整候选排序；反馈不得自动修改审核状态。
- embedding 索引保持可重建，资产文件和稳定 `asset_ref` 才是事实来源。

不引入：未审核素材自动发送、根据模型输出直接改标签或将图片二进制复制进 Core 数据库。

### TTS 与未来 Voice Runtime

可参考：Cyrene 的音频响应治理和 Pipecat 类流式语音 pipeline。

优先改造：

- 当前 TTS 保持小插件，只负责受控文本合成、格式验证、音频元数据、路径 containment 和 TTL 清理。
- 统一返回 `request_id`、`duration_ms`、`audio_bytes`、`format_verified`、engine 和明确错误码。
- 增加空音频、伪造 content type、损坏文件、超时、并发请求、TTL 清理和路径越界测试。
- ASR、VAD、打断、流式播放、语音轮次和长连接状态机另建 Voice Runtime，再通过 Bridge/Core contract 接入。

不引入：把实时语音主循环、SoVITS 参数、设备状态或长连接会话写入 Core。

## 第一批实施顺序

### P0：可发布基线

1. 为全部附属插件建立稳定分支、Git 基线、版本号和可回滚标签。
2. 新增插件族兼容 manifest，记录仓库、版本、contract version、依赖关系和验证命令。
3. 建立统一只读 contract fixture，覆盖 health、版本、能力、超时和错误响应。
4. 完成干净目录安装、AstrBot 启动、插件加载、重启、迁移、备份恢复和卸载演练。

### P1：可靠性

1. Bridge 增加幂等与乱序事件测试。
2. Warehouse 增加备份恢复、删除传播和容量基准。
3. Workflow Center 增加 proposal benchmark 和 contract drift fixture。
4. Skill Center 增加供应链与路径安全测试。
5. Gallery/TTS 增加资源生命周期测试。

### P2：陪伴体验

1. Core 新增只读 ExplanationService，统一解释需求、可用能力、治理结果、证据和限制。
2. Gallery 建立 scene/emotion 候选与反馈闭环。
3. Memory 建立冲突、更正、共同回忆和关系连续性评测。
4. Proactive 层先增加场景评分、冷却和反馈解释，不直接扩大主动发送权限。
5. 有真实实时语音需求后再独立建设 Voice Runtime。

## 验收标准

- 每个新增机制都能指出来源项目、吸收点、拒绝项和 Plana contract 落点。
- 任意跨插件任务使用同一 task/run id 查询 route、policy、confirmation、backend、事件和终态。
- 网络失败与空结果可区分，重复回调不产生重复写入或重复主动发送。
- Warehouse 可从备份恢复，索引可重建，删除能传播，Core 不依赖其内部 Store。
- Skill、Gallery、Workflow 和语音候选均不能绕过 Core 执行授权。
- 同一兼容 manifest 可在干净环境重建插件族并运行项目既有验证。

## 当前建议

当前不应继续增加新的大框架依赖。最有价值的工作顺序是：先完成 P0 发布基线，再完成 Bridge 幂等和 Warehouse 恢复闭环，然后用 benchmark 决定 Workflow Center 是否值得独立存在。体验层优化应优先投入 ExplanationService、Gallery 候选反馈和记忆冲突评测，而不是扩充更多 capability 名称。
