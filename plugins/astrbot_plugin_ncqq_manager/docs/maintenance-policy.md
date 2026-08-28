# 维护约束

本文定义后续修改本插件时必须遵守的边界。它面向后续模型和维护者，优先级高于临时任务记录。

## 修改边界

- 不新增 `scripts/` 目录。
- 不新增根目录 README 之外的 README 文件。
- 不把本地 token、API key、远端配置、运行日志写入仓库。
- 不在代码中写大量解释性注释；长期说明放入 `docs/` 下功能命名文档。
- 不恢复旧命令别名体系；聊天侧统一走 workflow。
- 不为 WeChat adapter 加兼容分支；正式平台只按 OneBot v11 / `aiocqhttp`。

## 文档边界

稳定架构文档进入 git：

- `docs/architecture.md`
- `docs/module-map.md`
- `docs/configuration.md`
- `docs/data-storage.md`
- `docs/multi-manager-architecture.md`
- `docs/workflows.md`
- `docs/workflow-catalog.md`
- `docs/workflow-engine.md`
- `docs/group-chat-routing.md`
- `docs/approval-model.md`
- `docs/operation-flows.md`
- `docs/core-services.md`
- `docs/astrbot-tools.md`
- `docs/rendering-assets.md`
- `docs/plugin-pages-architecture.md`
- `docs/plugin-compliance.md`
- `docs/maintenance-policy.md`

临时文档不进入 git：

- `local-docs/`
- `docs/current/`
- `HANDOFF*.md`

若临时文档中的内容需要长期保留，必须整理到稳定文档中，而不是取消 ignore。

## 架构同步规则

| 修改内容 | 必须同步的文档 |
| --- | --- |
| 目录结构、模块边界 | `docs/architecture.md`、`docs/module-map.md` |
| `_conf_schema.json` 配置项 | `docs/configuration.md`、`docs/plugin-compliance.md` |
| KV key、绑定结构、审批记录、健康快照 | `docs/data-storage.md` |
| 多 manager 配置、权限或 client 生命周期 | `docs/multi-manager-architecture.md` |
| workflow 名称、参数、路由规则 | `docs/workflow-catalog.md`、`docs/workflow-engine.md` |
| 具体流程顺序 | `docs/operation-flows.md` |
| 群聊触发、白名单、OneBot 消息判定 | `docs/group-chat-routing.md` |
| 审批动作、审批回复、执行安全 | `docs/approval-model.md` |
| 底层 API 封装或 client 行为 | `docs/core-services.md` |
| AstrBot tool、命令入口或 mixin 行为 | `docs/astrbot-tools.md` |
| HTML 渲染、模板、素材目录 | `docs/rendering-assets.md` |
| Plugin Pages 页面、bridge API 或 WebUI 操作边界 | `docs/plugin-pages-architecture.md`、`docs/plugin-compliance.md` |
| metadata、schema、logo、requirements、平台声明 | `docs/plugin-compliance.md` |

## 大文件限制

- Python、Markdown、JSON、YAML、HTML 文件单文件不超过 500 行。
- 大流程文档必须按功能拆分，不把 Mermaid、选择规则、群聊规则和审批规则堆在同一文件。
- 代码文件接近 500 行时，优先按职责拆模块，而不是压缩可读性。
- 模板文件接近 500 行时，优先拆局部模板或减少重复 CSS。

## 发布前检查

```powershell
python -X utf8 -m compileall main.py core tools workflows rendering
python -X utf8 -c "import json; json.load(open('_conf_schema.json', encoding='utf-8')); print('json ok')"
git diff --check
```

额外建议：

- 检查所有正式文档链接是否存在。
- 扫描仓库中是否出现 `sk-`、长 token、明文 API key。
- 确认 `git status --short --ignored` 中临时文档仍为 ignored。
