# rendering 模块

`rendering` 定义渲染端口，隔离业务模块和具体 HTML 渲染实现。

## 文件职责

- `renderer_port.py`: 渲染接口协议。
- `html_renderer_adapter.py`: 将 `utils.html_renderer.HtmlRenderer` 适配为端口实现。

## 维护说明

- Handler 和主题渲染应依赖 `RendererPort` 或具体 theme，不直接操作 Playwright。
- 如果未来替换渲染实现，优先在这里加适配器。
- 当前默认输出 PNG，并启用透明背景；需要透明裁剪时优先传具体 selector。
- HTML 渲染失败默认重试一次；重试前会回收 Playwright browser 和 driver，避免复用异常浏览器状态。
- Playwright browser 作为进程内单例复用；每次渲染新建并关闭 context/page。browser 达到渲染次数或存活时间上限后会软回收。
- HTML 渲染前会把模板中的 `face`/`avatar` 字段转换为本地 data URI，并复用 `image_cache/avatars/` 磁盘缓存；`cover` 字段会在进入 Playwright 前压缩或降级，避免订阅卡片、候选卡片、账号卡片和链接解析卡片反复拉取远程资源。
- 直播/动态卡片的头像和主封面在压缩失败时使用本地 data URI 降级图，避免已超时的外链继续进入 Playwright 并拖慢截图。头像缓存过期后刷新失败时优先使用旧缓存；没有旧缓存时使用本地默认头像。
- 业务模块只关心 `render()` 输入输出，不应知道浏览器启动、页面等待或截图细节。
- 新增渲染实现时保持 `RendererPort` 方法签名稳定，再逐步替换调用方注入。
- 渲染失败要向调用方返回明确异常，让 handler/workflow 能给用户可读提示。
