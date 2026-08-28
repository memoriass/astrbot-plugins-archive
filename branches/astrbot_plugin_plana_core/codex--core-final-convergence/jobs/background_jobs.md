# Background Jobs

`jobs/` 维护 Plana Core 生命周期托管的异步后台任务。后台任务不授予新权限，只周期性调用已经存在的 runtime/service 能力。

## 文件职责

- `manager.py`: `RuntimeJobManager`，负责注册、启动、停止、状态汇总和错误记录。

## 当前 Job

- `maintenance`: 在配置启用后周期性调用 `global` 加最近活跃 scope 的 memory maintenance；concept accumulation 仍只在 `global` 执行，然后处理 state decay、proactive delivery 和 proactive cleanup。

## 维护规则

- job 必须由插件生命周期启动和停止，不能遗留裸 task。
- job handler 内部仍需遵守原服务边界；写入、删除和主动发送不得绕过确认路径。
- 状态 payload 只暴露摘要和最后错误，不暴露 token、secret 或完整用户内容。
