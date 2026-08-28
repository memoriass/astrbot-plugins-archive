# 多 Manager 架构

本文说明插件如何同时管理多个 ncqq-manager 面板。这里的 manager 指 ncqq-manager 控制面板；BotShepherd/radar endpoint 仍属于各自面板内部的后端端点。

## 配置模型

面板配置统一使用 `_conf_schema.json` 中的 `manager_profiles` 模板列表。`default_manager` 控制未显式指定时使用的面板。配置字段和示例见 [configuration.md](configuration.md)。

## Manager ID

- ID 会被规范化为小写。
- 只保留字母、数字、`-`、`_`，其他字符替换为 `-`。
- 空 ID 会生成 `manager-序号`，实际配置时应显式填写稳定 ID。
- 未知 ID 必须报错，不允许静默回退默认面板。

## Client 生命周期

`core/client.py` 中的 `NCQQClientRegistry` 负责：

- 解析 `manager_profiles` 模板列表。
- 按 manager ID 懒加载 `NCQQClient`。
- 为每个 manager 复用独立 `aiohttp.ClientSession`。
- 插件卸载时关闭所有已创建 client。

业务代码必须通过 `plugin.client_for_manager(manager_id)` 获取 client。`plugin.client` 仅作为默认面板便捷入口。

## 实例引用

实例权限和绑定使用 `manager/instance`：

- `local/foo`
- `cloud/foo`

旧数据 `instances: ["foo"]` 只在默认面板兼容。非默认面板必须使用完整引用，避免本地和云端同名实例串权限。KV 结构见 [data-storage.md](data-storage.md)。

聊天入口支持两种写法：

```text
/ncqq query instances manager=cloud
/ncqq manage_instance control restart cloud/foo
```

LLM 工具参数支持 `manager`、`manager_id`、`panel`、`site`，统一解析到 `WorkflowRequest.manager_id`。

## 权限边界

- 普通用户只能操作已绑定的同 manager 实例。
- 管理员仍可跨 manager 操作，但必须显式落到某个 manager client。
- 一次工具调用不支持跨 manager 批量操作，应按 manager 拆分。
- `_resolve_target()` 负责 `manager/instance` 解析和单绑定自动推断。

## 审批边界

以下高权限动作必须在审批记录中保存 `manager_id`：

- `create_instance`
- `delete`
- `inject_backend`

管理员批准后，处理函数必须从审批参数取回 manager，并通过对应 client 执行。找不到 manager 时返回明确错误，不回退默认面板。

## 健康检查

定时掉线检测会遍历所有 configured manager：

- 每个 manager 独立读取实例列表。
- 快照 key 使用 `manager/instance`。
- 私聊和群告警展示完整引用。
- 旧默认面板纯实例名绑定继续匹配 owner。

## 维护要求

- 新增任何实例、后端、二维码、配置读取能力时，都要确认 `manager_id` 已向下传递。
- 新增 workflow 时必须在 `docs/workflow-engine.md` 和 `docs/workflow-catalog.md` 同步说明。
- 修改权限或审批行为时必须同步 `docs/approval-model.md`。
- 不得把真实 token、远端配置或本地测试日志写入仓库。
