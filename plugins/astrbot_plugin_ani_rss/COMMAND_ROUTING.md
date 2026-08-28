# Command Routing

命令路由负责 AstrBot wake prefix、显式命令、短任务 ID 和旧格式拒绝。

## 相关文件

- `routing/commands.py`: 命令名、wake prefix 格式化、短任务 ID 标准化、快捷命令过滤器。
- `main.py`: 注册 AstrBot 命令、Agent 工具和过滤器。

## 当前规则

- 主命令：`anirss`
- 别名：`ani-rss`、`ani`、`追番`、`番剧订阅`
- 挂起任务快捷命令：`ani` + 任务 ID 前几位或后几位。
- 短任务命令会识别 AstrBot 全局 `wake_prefix`；如果消息尚未被全局唤醒，也会尝试识别 `provider_settings.wake_prefix`，用于 `plana ani68d2 1`。

示例：

```text
/ania38d 1
plana ania38d 1
```

## 不支持格式

- `ani-xxxx`
- 裸短码，例如 `68d2 1`
- `继续anixxxx 1`

这些格式会被拦截并提示用户改用 `/ani68d2 1` 形式，避免落入默认 LLM 回复。
