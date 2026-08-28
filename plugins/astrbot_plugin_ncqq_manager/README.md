# AstrBot Plugin: ncqq-manager

NapCatQQ 容器控制与后端路由管理插件。插件面向 OneBot v11 场景，提供实例状态查询、登录恢复、生命周期控制、后端接入、内部健康监控和审批队列。

维护和接手请先看：

- [架构说明](docs/architecture.md)
- [模块结构说明](docs/module-map.md)
- [配置说明](docs/configuration.md)
- [数据存储模型](docs/data-storage.md)
- [工作流说明](docs/workflows.md)
- [多面板架构](docs/multi-manager-architecture.md)
- [维护约束](docs/maintenance-policy.md)
- [插件合规检查](docs/plugin-compliance.md)

## 能力

- 通过统一 LLM 工具 `ncqq_manager` 调用 ncqq 工作流。
- 通过 `/ncqq` 命令进行确定性调试和人工触发。
- 在 AstrBot WebUI 中提供 `ncqq-dashboard`，查看多面板状态并处理审批。
- 支持同时配置多个 ncqq-manager 面板，用 `manager/instance` 区分本地和云端实例。
- 普通用户只可操作已绑定实例。
- 创建、删除、后端接入等高权限动作进入审批队列。
- 管理员可读取消息、审计、资源和配置诊断信息。
- 健康检查只保留给插件内部、Plugin Pages 和定时监控，不通过自然语言 LLM 工具或 `/ncqq` 外部命令暴露。
- 实例列表、绑定关系和告警支持 HTML 转图片，渲染失败时回退文本。

## 安装

1. 将插件目录放到 `AstrBot/data/plugins/astrbot_plugin_ncqq_manager`。
2. 安装依赖，AstrBot 会读取根目录 `requirements.txt`。
3. 在 AstrBot WebUI 的插件配置中通过“管理器面板列表”添加 ncqq-manager 地址、API key 和显示名称。
4. 平台使用 OneBot v11，也就是 AstrBot 的 `aiocqhttp` 适配器。

聊天或调试命令中可写 `manager=cloud`，也可把实例写成 `cloud/mybot`。

## 工作流入口

聊天场景优先使用主工作流：

| workflow | 用途 |
| --- | --- |
| `manage_instance` | 实例主流程，按 `intent` 路由到创建、重登、控制、检测、列表、销毁等动作。 |
| `query` | 查询主流程，按 `scope` 查询实例、后端、消息、审计、资源或配置。 |
| `manage_backend` | 后端主流程，查看端点或把已有端点接入实例。 |
| `review_approvals` | 管理员审批队列，支持 list/approve/reject。 |

细分工作流仍可直接调用，主要用于模型已经明确目标场景时：

- `create_instance`
- `relogin_instance`
- `control_instance`
- `connect_backend`
- `check_instance`
- `list_instances`
- `check_backends`
- `read_bot_messages`
- `audit_operations`
- `inspect_resources`
- `read_instance_config`
- `delete_instance`

## 调试命令

使用 AstrBot 唤醒前缀加 `/ncqq`：

```text
/ncqq help
/ncqq query instances
/ncqq query backends manager=cloud
/ncqq manage_instance control restart <实例名>
/ncqq manage_instance control restart cloud/<实例名>
/ncqq manage_backend connect <端点别名> <实例名>
/ncqq review_approvals
/ncqq review_approvals approve <审批ID>
```

## 项目结构

```text
main.py                AstrBot 生命周期、LLM 工具和命令入口
core/                  HTTP 客户端、API 动作、审批、健康检查
tools/                 AstrBot 工具混入和审批快捷入口
workflows/             业务工作流路由、解析、权限和格式化
rendering/             HTML 转图片与文本降级
templates/             HTML 模板
pages/                 AstrBot WebUI 插件页面
docs/                  架构与维护说明
```

## 发布检查

```powershell
python -X utf8 -m compileall main.py core tools workflows rendering
python -X utf8 scripts/verify_release.py
python -X utf8 -c "import json; json.load(open('_conf_schema.json', encoding='utf-8')); print('json ok')"
python -X utf8 -c "import sys, pathlib; sys.path.insert(0, str(pathlib.Path('..').resolve())); import astrbot_plugin_ncqq_manager.main; print('import ok')"
node --check pages/ncqq-dashboard/app.js
node --check pages/ncqq-dashboard/dashboard-renderers.js
node --check pages/ncqq-dashboard/dashboard-utils.js
git diff --check
```

## License

GPL-3.0
