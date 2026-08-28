# renderers 模块

`utils/renderers` 放推送卡片主题，把内部 `Post` 转成 AstrBot 消息组件。

## 文件职责

- `base.py`: 主题抽象基类。
- `movie_card.py`: 直播和类视频卡片主题。
- `dynamic_card.py`: 动态卡片兼容包装，复用现有 `dynamic_movie_card.html.jinja` 模板。

## 维护说明

- 新主题应只负责选择模板和组织模板数据。
- 不要在主题里做网络抓取或订阅状态判断。
- 主题默认模板必须存在于 `utils/resources/templates/`；不要保留指向已删除模板的默认值。
- 主题返回 AstrBot `message_components` 列表。
- 主题输入是内部 `Post`，新增展示字段时先扩展模型和解析器，再更新主题模板数据。
- 推送卡片会在渲染前通过 `utils/image_optimizer.py` 处理直播封面、动态 hero 和头像，避免 10MB 级主图直接进入 Playwright；头像会复用本地磁盘缓存，正文多图不做预压缩，压缩失败回退原图 URL，超出硬上限的主图会跳过。
- 动态和直播卡片仍使用推送模板风格，不跟随 WebUI 管理页的背景设计。
- 透明背景由 HTML 渲染器和模板共同保证，主题不应强制添加整页背景。
- 推送时间通过 `display_timezone` 和 `utils/timezone.py` 格式化，默认 `Asia/Shanghai`，避免服务器默认 UTC 导致卡片时间少 8 小时。
