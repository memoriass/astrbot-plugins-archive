# Rendering And Assets

`rendering` 负责把 HTML 模板渲染为 AstrBot 可发送图片，并提供文本降级。正式插件图标只保留根目录 `logo.png`。

## Rendering

| 文件 | 职责 |
| --- | --- |
| `rendering/html_renderer.py` | 实例列表、绑定关系、健康告警 HTML 转图片。 |
| `rendering/browser.py` | Playwright 浏览器复用、HTML 截图和卸载清理。 |
| `templates/instances.html` | 实例列表模板。 |
| `templates/bindings.html` | 绑定关系模板。 |
| `templates/alert.html` | 健康告警模板。 |

维护约定：

- 模板文件放在根目录 `templates/`。
- 渲染失败必须提供文本降级，避免功能不可用。
- 不在本层读取远端 API 或处理权限。

## Assets

| 文件 | 说明 |
| --- | --- |
| `logo.png` | 根目录正式插件图标，256x256 透明 PNG，AstrBot 与 ncqq 看板娘拥抱形象。 |
| `pages/ncqq-dashboard/assets/mascot-ncqq.png` | Dashboard 背景层左侧 ncqq 看板娘透明 PNG。 |
| `pages/ncqq-dashboard/assets/mascot-astr.png` | Dashboard 背景层右侧 AstrBot 看板娘透明 PNG。 |
| `pages/ncqq-dashboard/assets/fx-snow.svg` | ncqq 侧雪花粒子背景。 |
| `pages/ncqq-dashboard/assets/fx-stars.svg` | AstrBot 侧星尘背景。 |
| `pages/ncqq-dashboard/assets/backgrounds/sora-shattered-star-bg-v7-generated-fill.png` | 当前一级碎镜菜单背景图，已补齐下半部暗色空间，用于承载中心奇点和手掌碎片氛围。 |
| `pages/ncqq-dashboard/assets/memory-shards-generated-v2.png` | Dashboard 一级菜单破镜源图，保留用于追溯生成结果和重新裁切。 |
| `pages/ncqq-dashboard/assets/memory-shards/*.png` | 从整屏破镜视觉层裁切出的单片透明 PNG，供后续单片动效或局部替换使用。 |
| `pages/ncqq-dashboard/assets/memory-shards/manifest.json` | 单片镜片的源图裁切框、多边形点位、自然尺寸和百分比位置清单。 |
| `pages/ncqq-dashboard/assets/memory-shards-scene/*-scene-v14.png` | 当前 Dashboard 一级菜单实际渲染的单片镜片；完整玻璃底图保留，只裁已确认溢出的看板娘贴图区域。 |
| `pages/ncqq-dashboard/assets/memory-shards-scene/manifest.json` | scene-v14 镜片的来源、贴图裁切策略和对应基础单片信息。 |
| `pages/ncqq-dashboard/assets/memory-shards-alert/*-alert-red-v17.png` | manager 离线状态使用的柔和红色半边玻璃边缘光贴图。 |
| `pages/ncqq-dashboard/assets/memory-shards-alert/*-alert-yellow-v17.png` | 审批入口使用的柔和黄色半边玻璃边缘光贴图；顶中碎片只保留底部短边提示，不使用右侧错误高光。 |
| `pages/ncqq-dashboard/assets/memory-shards-alert/manifest.json` | alert-edge-v17 贴图的来源、颜色变体和边段选择规则。 |

Dashboard 当前一级碎镜菜单使用 `sora-shattered-star-bg-v7-generated-fill.png` 作为受控背景，并在镜片层外加边缘模糊遮罩；旧的 v3/v4/v5 背景候选已移除，不再保留未引用大图。透明 ncqq/AstrBot 看板娘素材仍保留给非 memory 背景层或后续页面复用。
