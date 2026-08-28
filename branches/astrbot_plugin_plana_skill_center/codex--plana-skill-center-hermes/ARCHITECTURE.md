# Plana Skill Center 开发架构

Plana Skill Center 管理可长期复用的生成技能。Skill 与 workflow 不同：workflow 是一次性受控计划，skill 是可能影响未来对话的持久行为说明，因此需要隔离治理、扫描、审批、来源记录和导出完整性检查。

本插件只治理 `SKILL.md` 内容，不安装、不启用、不执行 skill。

## 治理链路

```text
draft/import
-> quarantine
-> static scan
-> approval policy
-> body/provenance hash
-> approved export
-> external trusted runtime decides use
```

## 模块边界

- `main.py`: AstrBot loader。
- `plugin/runtime.py`: 生命周期、命令、HTTP API、可选 LLM tool 和本机回环校验。
- `plugin/config.py`: 配置规整。
- `skills/models.py`: contract 常量和 dataclass。
- `skills/scanner.py`: 静态扫描规则。
- `skills/integrity.py`: body/file hash 和 export manifest helper。
- `skills/references.py`: reference manifest 路径 containment、文件数和总字节预算。
- `skills/store.py`: draft 生命周期 SQLite 持久化。
- `skills/manager.py`: propose、approve、reject、export 和 policy facade。
- `diagnostics/doctor.py`: 只读治理诊断，检查 loopback posture、dangerous approval、scanner version 和 export drift。

入口保持薄。治理规则放入 `skills/`，诊断放入 `diagnostics/`，AstrBot wiring 放入 `plugin/`。

## 生命周期

1. 生成或导入的 skill 通过命令、HTTP 或可选 LLM tool 提交。
2. manager 将 body 规整为 `SKILL.md` 形态。
3. scanner 返回 verdict 和 findings。
4. manager 记录 body hash、scanner version、source URI、origin model，并以 `quarantined` 保存。
5. 用户或管理员 approve/reject。
6. approved draft 可导出到 `approved/<id>-<slug>/SKILL.md`，导出前检查 approved hash drift，并写入 `plana-skill.json`。
   manifest 包含 `read_policy`、`reference_manifest`、`integrity_status`、ruleset hash 和 provenance，用于下游只读读取纪律与来源追踪。
7. 后续安装、启用或运行必须由其他可信层决定。

## Approval Policy

- `safe` 和 `caution` 可以审批。
- `dangerous` 默认禁止审批，除非显式开启 `allow_dangerous_approval=true`。
- 所有 HTTP endpoints 只接受无代理转发头的本机回环请求；跨主机、反代、公网入口不支持。
- `register_llm_tool` 默认关闭，因为 propose 会写入 durable quarantine state。
- `/plana-skill` 写命令默认关闭；开启 `enable_write_commands=true` 后仍必须带显式 `confirm`。
- 导出 hash drift 会在 doctor 中报 high risk。

## Core 集成边界

Plana Core 可以只读读取 exported skill draft 作为 recipe candidate。Core 不安装、不启用、不执行 `SKILL.md`，真实执行权仍来自 Core capability registry。
Core 只能读取 manifest、受限正文片段和 manifest 声明的 reference；`read_policy` 与 `reference_manifest` 不能授予执行权限。
用户层面的 Skill/能力调用必须先由 Plana Core Dialogue Center 识别为明确使用意图；本插件不能自行监听聊天、决定调用时机，或把 exported skill 变成运行时能力。

## 维护规则

- 新扫描规则必须包含 pattern id、severity、category 和描述。
- contract/version 字段变更必须同步 Core adapter、README 和验证脚本。
- 导出 manifest 新字段必须保持向后兼容。
- `plugin/runtime.py` 接近 500 行时拆分 command/API handler。

## 验证

```powershell
python -m compileall -q .
python scripts\check_skill_center.py
git diff --check
```
