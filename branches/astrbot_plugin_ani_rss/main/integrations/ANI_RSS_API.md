# ANI-RSS API

ANI-RSS API 访问层。

## 文件

- `ani_rss.py`: `AniRssClient` 和 `AniRssError`，负责 HTTP 请求、错误归一化和 API 响应拆包。

## 已使用/验证接口

- `GET/POST /ping`: 连通性检查。
- `POST /rssToAni`: 从 RSS URL 生成 ANI-RSS 订阅对象。
- `POST /addAni`: 添加订阅。
- `POST /deleteAni?deleteFiles=false`: 删除订阅。客户端已封装，当前仅用于发布验证清理和维护，不暴露给用户 workflow。
- `POST /previewAni`: 预览订阅可下载条目。
- `POST /listAni`: 获取订阅列表。
- `POST /refreshAni`: 刷新单个订阅。
- `POST /refreshAll`: 刷新全部订阅。
- `POST /mikan`: 搜索 Mikan。
- `POST /mikanGroup`: 获取 Mikan 字幕组 RSS。

## 约束

- API Key 只通过请求头 `api-key` 发送。
- 客户端不修改 ANI-RSS 的下载语义字段，例如 `lastDownloadTime`、下载路径、过滤规则。
- 删除订阅默认 `deleteFiles=false`，避免验证或维护操作删除本地媒体文件。
- `flatten_ani_list()` 只负责把 ANI-RSS 的周表结构压平成订阅列表，不做业务筛选。
