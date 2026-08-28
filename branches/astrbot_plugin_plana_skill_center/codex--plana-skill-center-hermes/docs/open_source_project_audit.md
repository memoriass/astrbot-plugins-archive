# Skill Center 开源项目代码审计

审计日期：2026-07-12

## 1. 当前仓库基线

- 分支 `codex/plana-skill-center-hermes`，版本 `0.1.0-beta.1`，审计时有 9 个未提交项。
- 生命周期为 quarantine → scan → approve/reject → hash/integrity → export；插件不安装、不启用、不执行 skill。
- `skills/scanner.py`、`integrity.py`、`store.py`、`manager.py` 已按职责拆分；SQLite 保存 draft 与审批来源。
- 导出 `SKILL.md` 与 `plana-skill.json`，manifest 已包含 `read_policy`、`reference_manifest`、`integrity_status`。
- 2026-07-12 验证：compileall、`scripts/check_skill_center.py`、`git diff --check` 均通过。

## 2. 发现清单

### P0

- 无 P0 代码缺陷；当前未提交状态仍阻止可复现发布。

### P1

1. **静态字符串扫描不足以构成供应链信任。** 当前能识别明显 prompt injection 和危险代码，但无法证明来源、作者身份、依赖内容或 reference 未被替换。
2. **reference manifest 读取纪律已定义但测试深度不足。** 需要覆盖符号链接、junction、大小写路径、Unicode 归一化、循环引用、超大文件和导出目录逃逸。
3. **来源字段缺少可验证身份。** `source_uri` 和 `origin_model` 可记录，但没有 source digest、签名、获取时间、上游 commit/tag 和许可证声明。
4. **产品定位仍容易与 AstrBot Skills 混淆。** Skill Center 应明确只治理候选配方；AstrBot 负责 skill discovery，Core capability 决定可执行权限。
5. **扫描规则版本化不够细。** scanner version 是整体字符串，缺少规则集 hash、规则启停原因和重新扫描迁移策略。

### P2

1. **不需要自建完整签名基础设施。** Sigstore/cosign 可作为发布来源验证参考，但本地 agent-created draft 更适合 hash、provenance 和人工审批。
2. **executable hint 容易被误解。** 应更名或明确为 capability mapping hint，且只能匹配已存在 registry。

## 3. 开源候选矩阵

| 项目 | 许可证/近期状态 | 可借鉴机制 | 依赖成本 | 裁决 |
| --- | --- | --- | --- | --- |
| `agentskills/agentskills` | Apache-2.0；2026-07-10 推送；无 release | SKILL.md 结构、渐进披露、互操作规范 | 低 | 作为格式兼容参考 |
| AstrBot Skills（本地） | 宿主实现 | discovery、active state、persona skill 绑定 | 已有依赖 | 第一运行时来源 |
| `sigstore/cosign` | Apache-2.0；2026-07-10 推送；release `v3.1.1` | 签名、provenance、透明验证思路 | 高，不宜作为插件运行依赖 | 借发布验证模型 |
| Cyrene-Agent（本地） | 本地参考 | manifest-only reference、路径 guard、单轮去重 | 不作为依赖 | 直接适配读取纪律 |

官方来源：

- `https://github.com/agentskills/agentskills`
- `https://github.com/sigstore/cosign`

## 4. 深审结论

### 可直接借鉴

- Agent Skills 的标准 frontmatter/目录约定和渐进披露语义，但保留 Plana governance manifest。
- Cyrene 的 manifest-only reference、路径 containment、单轮读取去重和总字节预算。
- 软件供应链中的 provenance：来源 URI、commit/tag、抓取时间、内容 digest、许可证和审核者。

### 需适配借鉴

- cosign 风格验证只用于可信上游发布包；本地草案继续使用 hash + 人工审批，不要求部署签名服务。
- AstrBot Skill active/persona 状态只作为只读 availability；Skill Center 不改变 AstrBot 启停状态。
- 外部 Agent Skills 兼容导入后必须重新扫描并进入 quarantine，不能因格式标准化而自动信任。

### 禁止引入

- 自动安装、自动更新、自动执行和网络拉取后直接启用。
- SKILL.md 或 reference 声明新的 executor、shell 权限或绕过 Core confirmation。
- 将静态扫描 `safe` 等同于可信或无副作用。

## 5. 目标架构与数据流

```text
local/generated/imported skill
  -> immutable source snapshot + provenance
  -> quarantine + versioned scanner
  -> human approval
  -> content/reference manifest + integrity hash
  -> exported advisory recipe
  -> AstrBot discovery + Core capability intersection
```

产品文案固定为“技能说明与流程配方治理”。Skill Center 不拥有运行时能力。

## 6. 实施任务

1. **扩展 provenance**：记录 source type、URI、commit/tag、retrieved_at、license、body/reference digest 和 reviewer。
2. **reference 安全测试**：覆盖 symlink/junction、`..`、绝对路径、Unicode、大小写、循环、超大文件和文件替换竞态。
3. **读取预算 V1**：manifest 声明允许文件；Core adapter 限制单文件、总字节、文件数和单轮重复读取。
4. **规则集版本化**：生成 scanner rules hash，保存每条 finding 的 rule version；规则升级触发重新扫描状态而非静默沿用。
5. **Agent Skills 兼容映射**：兼容标准字段，未知字段保留为 metadata；任何导入仍进入 quarantine。
6. **上游签名可选验证**：仅对声明签名的发行包验证并记录结果；失败降级为 untrusted，不阻塞本地草案流程。
7. **重命名 executable hint**：对外表达为 `capability_mapping_hints`，只能映射 Core 已登记 capability。

验证：现有 check，加恶意路径 corpus、TOCTOU、超大正文/reference、hash drift、规则升级和签名缺失/错误场景。

## 7. 最终裁决

- **立即实施**：provenance、reference 安全测试、读取预算、规则集 hash、产品定位修正。
- **验证后实施**：Agent Skills 兼容导入和可选签名验证。
- **暂缓**：远程 registry/market。
- **拒绝**：自动安装、自动执行、自动扩大 capability 和以 scan safe 替代审批。

## 8. 实施后复审（2026-07-12）

- scanner 现在输出稳定 ruleset hash，导出 manifest 同时记录 source、URI、origin model、content digest 和 retrieved time。
- 新增 reference validator，限制 16 个文件、256000 总字节，并拒绝绝对路径、路径逃逸、重复路径、symlink 和不存在文件。
- 专项测试覆盖 provenance、ruleset hash、合法 reference 和 `../` 路径逃逸。
- 仍待完成：真实导入 reference manifest、junction/TOCTOU corpus、规则升级重新扫描状态和可选签名验证。
# 2026-07-12 非干扰实施复审

- reference manifest 现在记录 SHA-256、字节数和 mtime，并提供导入前复验以发现文件替换。
- 本地测试覆盖 junction/symlink、Unicode 归一化、大小写重复、文件数/总字节预算和内容漂移。
- status 暴露 scanner ruleset hash 与 `rescan_required`，旧 ruleset 只要求重扫，不自动安装、启用或执行 skill。
