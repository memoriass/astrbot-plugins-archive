# Plana Skill Center

Plana Skill Center 是 Plana 插件族的 Skill 治理插件。它负责 quarantine、static scan、approval 和 export，不执行 skill，也不自动安装到 AstrBot。

## 边界

- 生成的 `SKILL.md` 先保存为 quarantined draft。
- 每个 draft 都记录 body hash、scanner version、source URI、origin model 和 approval/export hash。
- Dangerous scan result 默认不能审批。
- Approved draft 可导出到 `approved/<id>-<slug>/SKILL.md`。
- 导出时写入 `plana-skill.json`，并阻止 approved hash drift。
- `/status` 返回只读 `security_doctor`。
- Runtime execution、tool authorization 和用户确认属于 Core 或其他可信运行时。

## 命令

```text
/plana-skill status
/plana-skill list [status]
/plana-skill show <id>
/plana-skill approve <id> confirm
/plana-skill reject <id> confirm
/plana-skill export <id> confirm
/plana-skill propose confirm <name> | <SKILL.md body>
```

写命令默认关闭；只有配置 `enable_write_commands=true` 后才可使用，并且仍需显式 `confirm`。HTTP 写接口只接受本机回环请求，不提供跨主机 token 暴露。

## HTTP API

所有 HTTP endpoints 只接受无代理转发头的本机回环请求；跨主机、反代、公网入口不支持。需要跨边界时应由 Bridge Gateway 或专用网关重新设计。

- `GET /plana_skill_center/status`
- `GET /plana_skill_center/skills?status=quarantined&limit=50`
- `GET /plana_skill_center/skills/get?id=1&include_body=true`
- `POST /plana_skill_center/propose`
- `POST /plana_skill_center/approve`
- `POST /plana_skill_center/reject`
- `POST /plana_skill_center/export`

## 配置

- `enabled`: 启用插件。
- `register_llm_tool`: 注册 `plana_skill_propose`；默认关闭。
- `enable_write_commands`: 启用 `/plana-skill` 写命令；默认关闭，且仍需显式 `confirm`。
- `allow_dangerous_approval`: 允许审批 dangerous scan result；默认关闭。
- `max_skill_body_chars`: Skill body 最大字符数。

## Beta 状态

当前 beta 版本：`0.1.0-beta.1`。发布前执行：

```powershell
python -m compileall -q .
python scripts\check_skill_center.py
git diff --check
```

开发边界见 `ARCHITECTURE.md`。
