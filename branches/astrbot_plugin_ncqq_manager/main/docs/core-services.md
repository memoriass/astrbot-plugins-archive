# Core Services

`core` 是插件的底层服务层，不负责 AstrBot 入口编排。

| 文件 | 职责 |
| --- | --- |
| `core/client.py` | ncqq-manager HTTP 客户端与多面板 client registry。 |
| `core/actions.py` | 创建、删除、生命周期控制、后端注入等写操作。 |
| `core/monitoring.py` | 容器列表、资源、日志、文件、SSE 确认、后端端点读取。 |
| `core/interaction.py` | 登录状态刷新和二维码读取。 |
| `core/config_reader.py` | 容器内配置文件读取。 |
| `core/approval.py` | 审批 KV 队列、过期清理、原子领取。 |
| `core/health_check.py` | 定时掉线检测和通知。 |
| `core/offline_webhook.py` | 独立 HTTP 接收器，处理 ncqq-manager `plugin_api` 掉线 POST 并复用健康快照通知。 |

维护约定：

- 底层 API 返回尽量保持原始结构，由 `tools` 或 `workflows` 决定展示文案。
- 高权限用户侧操作不得绕过 `core/approval.py`。
- 多面板调用必须从插件实例获取 `client_for_manager(manager_id)`，不要直接假设 `self.client` 是唯一面板。
- 本层可以依赖 `rendering` 做健康告警图片，但不得依赖 `tools`。
- 掉线 POST 接收器不得注册为 LLM 工具或 Plugin Pages API；它只做 ncqq-manager 到插件内部通知链路的 HTTP 入口。
