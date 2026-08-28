# 群聊路由与 OneBot v11 判定

当前正式群聊场景只按 OneBot v11 标准消息考虑，平台为 AstrBot 的 `aiocqhttp` 适配器，不为 WeChat adapter 做额外分支。

## 消息格式

OneBot v11 群聊消息应使用数组格式：

```json
[
  {"type": "at", "data": {"qq": "123456"}},
  {"type": "text", "data": {"text": " ncqq 当前有哪些实例？"}}
]
```

显式 `/ncqq` 调试命令和自然语言工具调用是两条路径。

## 判定顺序

1. 原始文本显式以唤醒前缀调用 `/ncqq` 时，进入调试命令入口。
2. 群内 `@bot ncqq ...` 是自然语言请求，不进入 `/ncqq` 调试命令，由 AstrBot LLM 判断是否调用 `ncqq_manager`。
3. 询问实例状态、后端端点、消息、审计、资源或配置时，优先调用 `workflow=query`。
4. 普通聊天未提到 ncqq、NapCatQQ、实例、后端、管理器、BotShepherd 等管理语义时，不应调用本插件工具。

示例：

```text
/ncqq query instances
@bot ncqq 当前有哪些实例
@bot 帮我重启 cloud/mybot
```

## 响应群白名单

配置 `enable_group_whitelist=true` 后，插件只响应 `response_groups` 中列出的群聊。

`response_groups` 支持逗号、空格、顿号分隔多个群号。

该限制作用于：

- LLM 工具入口 `ncqq_manager`
- `/ncqq` 调试命令
- 群内审批快捷回复

私聊不受响应群白名单限制，用于管理员或绑定用户做必要排障。

## 工具调用边界

- 只在用户明确表达管理意图时调用工具。
- 只读查询优先走 `query` 主流程。
- 实例变更优先走 `manage_instance` 主流程。
- 后端端点相关优先走 `manage_backend` 主流程。
- 删除、创建、接后端等高权限普通用户请求进入审批，不直接执行。

## 多 Manager 群聊表达

群聊中推荐让用户明确面板：

```text
重启 cloud/mybot
查询 cloud 面板实例
把 astrbot 后端接到 local/mybot
```

模型应将这些表达解析为 `manager` 参数或 `manager/instance` 目标，而不是把 `cloud` 当作实例名的一部分。
