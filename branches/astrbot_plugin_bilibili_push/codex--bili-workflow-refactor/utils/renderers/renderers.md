# renderers 模块

`utils/renderers` 放推送卡片主题，把内部 `Post` 转成 AstrBot 消息组件。

## 文件职责

- `base.py`: 主题抽象基类。
- `movie_card.py`: 直播和类视频卡片主题。
- `dynamic_card.py`: Markdown 风格动态卡片主题，当前主流程主要使用 `dynamic_movie_card` 模板。

## 维护说明

- 新主题应只负责选择模板和组织模板数据。
- 不要在主题里做网络抓取或订阅状态判断。
- 主题返回 AstrBot `message_components` 列表。
- 主题输入是内部 `Post`，新增展示字段时先扩展模型和解析器，再更新主题模板数据。
- 动态和直播卡片仍使用推送模板风格，不跟随 WebUI 管理页的背景设计。
- 透明背景由 HTML 渲染器和模板共同保证，主题不应强制添加整页背景。
