# Plana 附属插件开源审计总矩阵

审计日期：2026-07-12

本文件只汇总六个附属插件的独立代码审计，不重新审计 Plana Core。详细证据、候选项目与任务位于各插件仓库的 `docs/open_source_project_audit.md`。

## 总体结论

- 六个插件现有 compile/check 均通过，Git 仓库的 `git diff --check` 也通过；Bridge、Gallery、TTS 存在 LF/CRLF 提示。
- Memory Warehouse 没有 Git 仓库，是插件族首要发布阻断项。
- TTS 在 `main` 保留未提交开发改动，是第二个版本纪律风险。
- 当前不建议新增大型运行时依赖。开源项目主要用于吸收评测、契约、幂等、供应链、候选排序和语音 pipeline 机制。
- Workflow Center 是否继续独立存在必须由固定 benchmark 决定；抽象完整度本身不是保留理由。

## 审计矩阵

| 插件 | 当前强项 | 最高优先缺口 | 主要参考 | 裁决 |
| --- | --- | --- | --- | --- |
| Memory Warehouse | evidence-only、稳定 ID、FTS、scope/actor、loopback contract | 无 Git；无备份恢复、删除传播和质量/容量 benchmark | Mem0、Letta、Graphiti | 保持 SQLite 事实源，暂缓 graph/vector 依赖 |
| Bridge Gateway | Core 同进程 adapter、Hermes relay、LAN/loopback、capability fail-closed | 统一幂等、Runner identity、callback/poll 竞态、artifact 独立状态 | Hermes Agent、MCP SDK、Cyrene、AstrBot | 保持 relay-only，禁止第二套 gateway/runtime |
| Workflow Center | Contract V3、proposal-only、hash echo、短 TTL cache | 缺少与 Core advisor 的质量/成本 benchmark | LangGraph、PydanticAI、Hermes | 先 benchmark，再决定独立或回收 |
| Skill Center | quarantine、扫描、审批、hash、manifest、禁止执行 | provenance、reference 路径 corpus、规则集 hash、产品定位 | Agent Skills、AstrBot Skills、Sigstore、Cyrene | 定位为技能说明与流程配方治理 |
| Gallery | 本地事实源、asset_ref、去重、needs-review、候选接口 | 引用完整性、生命周期事务、remote health、候选评测 | OpenCLIP、Immich、FiftyOne、Cyrene | 允许可重建 semantic candidate，禁止自动审核/发送 |
| TTS | 默认关闭、AstrBot provider、外部 backend 隔离、格式与 TTL | main 开发、错误 contract、SSRF/配额、运行期清理 | Pipecat、LiveKit Agents、Piper | TTS 保持小插件；实时语音另建 runtime |

## 跨插件依赖顺序

### M0：发布基线

1. Warehouse 建立 Git、首个 tag 和可恢复版本基线。
2. TTS 从 `main` 切 feature branch，确认未提交项归属。
3. 六插件冻结 metadata/version/contract 清单，形成插件族兼容 manifest。

### M1：统一可靠性契约

1. Bridge 定义 task/run/idempotency/terminal envelope。
2. Warehouse 定义 backup/restore 与 delete tombstone contract。
3. TTS 定义统一 error/retryable/verification metadata。
4. Gallery 定义 asset tombstone、review audit 和 remote mapping health。
5. Skill Center 定义 provenance、reference budget 和 ruleset hash。

### M2：评测与裁决

1. Workflow benchmark 比较 Core advisor、Center 和 deterministic fallback。
2. Warehouse benchmark 覆盖更正、冲突、过期、说话人、跨 scope 和容量。
3. Gallery benchmark 比较 tag-only、embedding-only 和 hybrid candidate。
4. 若 Workflow Center 未达到约定收益，制定回收兼容窗口。

### M3：可选体验扩展

1. Gallery 在 benchmark 证明收益后增加可选 OpenCLIP backend。
2. Warehouse 在关键词检索不足被量化后实验时间语义或可重建图索引。
3. 有真实实时通话需求后编写独立 Voice Runtime ADR，优先参考 Pipecat。
4. MCP 只在 Bridge 做 discovery/canonical candidate spike。

## 统一约束

- LLM、embedding、MCP、planner 和 semantic retrieval 只产生 proposal、candidate、evidence 或 explanation。
- Core 继续拥有 capability registry、风险、确认、执行、长期画像提升和审计。
- 附属插件不得直接写 Core SQLite，也不得通过 skill、MCP 或远端 planner 注册新 executor。
- 网络错误必须区别于空结果；重复 callback、poll、notification 和导入不得产生重复副作用。
- canonical 数据与派生索引分离：Warehouse SQLite evidence、Gallery 本地 asset/hash 是事实源；FTS、embedding、thumbnail 和 remote mapping 可重建。

## 开源依赖裁决

### 建议直接复用

- AstrBot persona/provider/skills/tool/session/Plugin Pages 和平台适配。
- 官方项目的 contract、测试 corpus、状态事件、provenance 和评测方法。

### 仅允许适配机制

- Mem0/Letta/Graphiti 的记忆评测与时间冲突。
- LangGraph/PydanticAI 的类型化输出、节点事件和有限重试。
- Sigstore 的 provenance/验证模型。
- OpenCLIP 的只读候选索引。
- Pipecat/LiveKit 的未来实时语音架构。

### 明确拒绝

- 完整第三方 agent runtime、第二套 gateway/session/provider。
- 自动记忆提升、自动 skill 安装执行、自动 MCP 授权。
- 未审核素材自动发送、远端 URL 作为资产事实源。
- Core 内实时音频主循环和设备控制。

## 验证记录

2026-07-12 实际执行：

- Warehouse：compileall 通过；`check_memory_warehouse_plugin.py` 通过；无 Git，未执行有效 diff check。
- Bridge：compileall、`check_bridge_gateway.py`、diff check 通过。
- Workflow Center：compileall、`check_workflow_center_contract.py`、diff check 通过。
- Skill Center：compileall、`check_skill_center.py`、diff check 通过。
- Gallery：compileall、`check_gallery_beta.py`、diff check 通过。
- TTS：compileall、`check_tts_plugin.py`、diff check 通过。

这些检查证明当前静态 contract 和临时目录 smoke flow，不证明真实 AstrBot 生命周期、生产数据库迁移、远程服务、并发或重启恢复。

## 实施后复审（2026-07-12）

| 插件 | 本轮完成 | 仍需后续 |
| --- | --- | --- |
| Warehouse | online backup、manifest/hash/integrity、restore candidate、显式幂等删除与删除审计 | Git、停服恢复、容量/冲突 benchmark、移除 direct fallback |
| Bridge | 持久终态 ledger、payload digest 重放、冲突终态拒绝、通知幂等 | 全阶段 envelope、Runner identity、callback/poll 集成竞态 |
| Workflow | 6-case 固定 proposal benchmark，当前 6/6 通过 | 真实 provider 与 Core advisor 对照后作独立/回收裁决 |
| Skill | ruleset hash、provenance、reference containment/预算 | reference 导入、junction/TOCTOU、重新扫描状态、签名验证 |
| Gallery | asset tombstone、显式候选反馈与 request id 幂等 | fault injection、remote health、反馈排序、semantic benchmark |
| TTS | 稳定错误 metadata、20 MiB 上限、managed path、同 host audio URL | 并发/目录配额、周期清理、redirect/DNS、decoder 深验 |

复审后总体判断：安全边界与可测试性明显改善，六插件专项检查全部通过；插件族仍不具备发布条件，原因仍是 Warehouse 无 Git、TTS 在 `main`、所有仓库存在未提交改动，以及真实 AstrBot/远端集成验证尚未完成。
