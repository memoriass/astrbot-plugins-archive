# Plana Skill Center（已退役）

> **本仓库已于 2026-07-21 退役。请勿在新部署中启用。**

Skill quarantine、扫描、候选审批和受控导出流程已收口到 Plana Core 的受控能力候选链。本仓库仅保留历史治理实现、SQLite schema 和导出格式供审计，不再提供运行时能力。

当前 AstrBot 入口是无副作用兼容壳：

- 不初始化数据库或创建数据目录；
- 不注册 `/plana-skill` 命令；
- 不注册 Web API；
- 不注册 `plana_skill_propose` LLM tool；
- 不扫描、审批、拒绝、导出或修改已有 Skill 数据。

历史命令、API 和配置不再受支持。退役范围与数据保留说明见 `RETIRED.md`。

## 验证

```powershell
python -m compileall -q .
python scripts\check_skill_center.py
git diff --check
```

归档结构见 `ARCHITECTURE.md`。
