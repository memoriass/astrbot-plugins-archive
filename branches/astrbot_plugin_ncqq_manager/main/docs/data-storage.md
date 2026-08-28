# 数据存储模型

插件使用 AstrBot 原生 KV 存储保存运行状态。本文记录稳定 key 和结构，便于后续迁移、排错和权限审查。

## `user_mapping`

用途：记录 QQ 用户与 ncqq 实例的绑定关系。

结构：

```json
{
  "123456": {
    "nickname": "可选昵称",
    "instances": ["local/foo", "cloud/bar"]
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| 顶层 key | `string` | QQ 号。 |
| `nickname` | `string` | 展示用昵称，可为空。 |
| `instances` | `list[string]` | 绑定实例列表，正式格式为 `manager/instance`。 |

兼容规则：

- 旧数据中的纯实例名只在默认 manager 下兼容。
- 新增绑定必须写入 `manager/instance`。
- 删除实例成功后，应移除同 manager 下对应绑定。
- 非默认 manager 不接受纯实例名绑定。

## `pending_approvals`

用途：记录等待管理员批准的高权限操作。

结构：

```json
{
  "ABC123": {
    "approval_id": "ABC123",
    "action": "delete",
    "params": {
      "manager_id": "cloud",
      "instance_name": "foo"
    },
    "requester_qq": "123456",
    "group_id": "987654",
    "description": "销毁实例 foo",
    "created_at": 1710000000.0
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `approval_id` | `string` | 六位大写字母数字 ID。 |
| `action` | `string` | 审批动作，目前包括 `create_instance`、`delete`、`inject_backend`。 |
| `params` | `dict` | 执行所需结构化参数，必须包含目标 `manager_id`。 |
| `requester_qq` | `string` | 申请者 QQ。 |
| `group_id` | `string` | 申请来源群号，可为空。 |
| `description` | `string` | 面向管理员展示的摘要。 |
| `created_at` | `float` | Unix timestamp。 |

安全规则：

- 审批执行只能依赖 `params`，不能从当前聊天上下文推断目标。
- 领取审批使用原子 claim，避免重复执行。
- 过期审批不执行远端请求。
- 缺失或未知 `manager_id` 必须报错，不回退默认 manager。

## `health_snapshot`

用途：定时掉线检测的上一轮在线状态快照。

结构：

```json
{
  "local/foo": true,
  "cloud/bar": false
}
```

规则：

- key 必须使用 `manager/instance`。
- value 为上一轮检测到的登录在线状态。
- 首次出现的实例不触发掉线或恢复通知。
- 新快照覆盖旧快照。
- ncqq-manager `plugin_api` 掉线 POST 会单点更新对应 key；若状态没有变化，不重复推送通知。

## 数据迁移要求

- 迁移旧绑定时，只能把纯实例名映射到默认 manager。
- 迁移脚本不得写入仓库；一次性本地工具放入 ignored 目录。
- 迁移前应导出原始 KV 数据备份。
- 迁移后需要验证非默认 manager 同名实例不会获得旧绑定权限。
