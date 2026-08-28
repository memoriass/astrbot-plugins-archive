# Plugin Pages 架构

本插件提供 `ncqq-dashboard` Page，用于在 AstrBot WebUI 中查看多 ncqq-manager 面板状态并处理审批。页面不替代聊天 workflow，也不编辑插件配置。

## 页面目录

| 路径 | 职责 |
| --- | --- |
| `pages/ncqq-dashboard/index.html` | AstrBot 扫描入口。 |
| `pages/ncqq-dashboard/dashboard-utils.js` | 页面文本转义、状态判定、时间和阈值等纯工具函数。 |
| `pages/ncqq-dashboard/dashboard-renderers.js` | 一级卡片和二级面板的 HTML 片段构造。 |
| `pages/ncqq-dashboard/app.js` | 通过 `window.AstrBotPluginPage` bridge 调用插件 API，维护状态、分页、弹窗和事件绑定。 |
| `pages/ncqq-dashboard/style.css` | 基础布局、侧栏和通用控件样式。 |
| `pages/ncqq-dashboard/layout.css` | 当前页面骨架、侧栏和弹窗布局。 |
| `pages/ncqq-dashboard/cards.css` | 二级实例卡、绑定卡和审批卡基础样式。 |
| `pages/ncqq-dashboard/glass.css` | 背景层、透明看板娘素材和整体光效。 |
| `pages/ncqq-dashboard/stage.css` | 一级 memory 镜片菜单，使用生成图视觉层和透明热区定位。 |
| `pages/ncqq-dashboard/detail.css` | 二级详情面板、实例卡片、绑定卡片、审批弹窗和分页筛选。 |
| `pages/ncqq-dashboard/preview-data.js` | 无 bridge 环境下的本地预览数据。 |
| `docs/plugin-pages-shard-visual.md` | 一级碎镜菜单的参考图识别、视觉规则和实现约束。 |

页面可在无 bridge 环境下使用预览数据渲染，便于本地检查多面板布局。正式运行时只通过 bridge 请求后端。
页面使用两级交互：

- 一级为整屏破镜拼图式菜单，每个 ncqq-manager 面板一个主碎片，绑定和审批各一个主碎片。
- 镜片视觉由 `assets/memory-shards-scene/*-scene-v14.png` 单片资源提供，HTML 按钮只作为透明热区。
- JS 动态生成的插件内图片 URL 通过 `dashboard-utils.js` 的 `assetUrl()` 继承 AstrBot 注入的 `asset_token` 和 `theme`；静态 HTML/CSS 资源继续交给 AstrBot Page 服务自动重写。
- 一级背景由 `assets/backgrounds/sora-shattered-star-bg-v7-generated-fill.png` 提供，玻璃层整体上移并保持轻微浮动；页面不再启用星河流动遮罩、A/C 背景试验或横向瀑布流。
- 原始破镜整图保留在 `assets/memory-shards-generated-v2.png`，基础单片裁切位于 `assets/memory-shards/`，由 `manifest.json` 记录源图裁切框和百分比位置。
- `assets/memory-shards-scene/manifest.json` 记录嵌入 ncqq/AstrBot 看板娘片段后的当前运行资源；scene-v14 保留完整玻璃底图，只裁已确认溢出的看板娘贴图区域，不做全局内缩。
- 上方暗色碎片固定为审批入口，下方暗色碎片固定为绑定关系入口；manager 节点只分配其余碎片。
- manager 存在离线实例时，一级碎片叠加 `assets/memory-shards-alert/*-alert-red-v17.png` 柔和红色半边边缘光。
- 审批入口存在待审批时叠加 `assets/memory-shards-alert/*-alert-yellow-v17.png` 柔和黄色半边边缘光；绑定入口不显示状态光。
- alert-edge-v17 继承修正后的 polygon 边段光，并按 scene-v14 的完整玻璃 alpha 裁切。
- hover 文案只显示节点名称，不使用信息面板。
- 第一阶段只做主镜片位置，不渲染外圈小碎屑，也不启用横向瀑布流。
- 点击一级卡片后进入二级弹窗。实例、绑定和审批互相独立，不把所有数据挤在同一视图。
- 实例二级面板按 9 个一页分页，并在顶部提供全部、异常、心跳、离线快速筛选。
- 绑定关系二级面板使用头像、目标实例和引用列表，便于快速定位。
- 审批二级面板只提供批准、拒绝，并使用统一确认弹窗。

## 后端 API

后端 API 在 `tools/page_api.py` 中注册，主路由前缀为 `/ncqq_manager`，并兼容保留 `/astrbot_plugin_ncqq_manager`。实现使用 AstrBot `context.register_web_api()` 加 Quart 的 `jsonify`/`request`，避免依赖未公开的 `astrbot.api.web`。

| Dashboard endpoint | 方法 | 说明 |
| --- | --- | --- |
| `dashboard/summary` | `GET` | 汇总 manager 健康、实例、审批、绑定和健康快照。 |
| `approvals/<approval_id>/approve` | `POST` | 原子领取审批并复用现有审批执行器批准。 |
| `approvals/<approval_id>/reject` | `POST` | 原子领取审批并拒绝。 |

Page 端调用 bridge 时不写插件名前缀，例如 `bridge.apiGet("dashboard/summary")`。

## 数据边界

- manager 信息只返回 ID、名称、URL 和状态，不返回 API key。
- Dashboard 按 manager 分组渲染，每个 ncqq-manager 面板独立展示健康、实例和容器摘要。
- 实例和绑定关系在各自二级面板内独立前端分页，`dashboard/summary` 仍一次返回当前摘要数据，不新增分页 API。
- 实例卡片数据来自目标 manager 的 `/api/containers` 和 `/api/bots`，包括昵称、UIN、头像、登录阶段、心跳和容器状态。
- 审批列表不返回原始 `params`，只返回页面展示所需的 manager、实例、后端别名和描述。
- 绑定关系只读展示，不在页面修改。
- 健康快照只展示 `manager/instance` 与在线状态。

## 操作边界

Page 第一版只允许审批：

- approve：调用 `claim_approval()` 后执行 `_dispatch_approved_action()`。
- reject：调用 `claim_approval()` 后移除记录。

不在 Page 中提供实例启动、停止、重启、二维码、后端端点查看/接入、配置编辑或批量跨 manager 操作。这些能力继续由聊天 workflow 和审批模型承接。

## 维护要求

- 修改 Page API 时同步本文和 `docs/plugin-compliance.md`。
- 修改页面 JS/CSS 拆分时同步本文，避免后续维护继续向入口文件堆逻辑。
- 新增页面目录时必须包含 `pages/<page_name>/index.html`。
- Page 后端不得绕过 `core/`、`tools/` 中已有的审批和数据读取逻辑。
- 不把真实 token、API key、本地 AstrBot 配置或远端日志写入页面资源。
