# core 模块

`core` 放跨模块共享能力，不包含具体命令和推送业务。

## 文件职责

- `types.py`: 插件内部标准类型，如 `Post`、`SubUnit`、`MessageSegment`。
- `models.py`: Bilibili API 的 Pydantic 模型。
- `http.py`: 全局 `httpx.AsyncClient`、SQLite 账号池读取、风控账号轮换。
- `network_retry.py`: 请求级网络容错，只对超时、连接错误和临时 HTTP 5xx 重试一次。
- `avatar_cache.py`: UP 头像 URL 的 KV 缓存和有限并发拉取队列，供 Web 管理页和订阅卡片复用。
- `platform.py`: 动态平台和状态平台的抽象基类。
- `config.py`: 插件配置解析和安全兜底。
- `compat.py`: Pydantic v1/v2 兼容入口。
- `runtime.py`: 插件运行期资源初始化、临时文件清理和最终消息发送。
- `utils.py`: 通用算法和 Bilibili WBI 签名。

## 维护说明

- Bilibili API 响应字段变化时，优先更新 `models.py`，再调整 `dynamic/`、`live/` 或 `parser/` 的转换逻辑。
- 任何跨 Pydantic v1/v2 的调用都应通过 `compat.py`，避免业务模块直接依赖版本差异。
- 插件启动配置统一通过 `config.py` 解析；新增配置项时同步 `_conf_schema.json`、`README.md` 和 `main.py` 装配字段。
- 用户可见卡片时间使用 `display_timezone`，默认 `Asia/Shanghai`；不要依赖服务器系统时区。
- `enable_parser_video_download` 默认关闭，只控制聊天链接解析的视频附件，不影响订阅动态推送。
- 长期 HTTP client 统一走 `HttpClient.get_client()`；新增网络访问时不要在 handler 或 workflow 中创建全局 client。
- 面向 Bilibili 的新增 GET 请求如需容错，应使用 `network_retry.py` 的请求级重试；不要重跑整个 workflow，避免重复创建 pending、重复发卡或重复写库。
- 订阅列表、管理页等批量头像查询统一走 `avatar_cache.py`，不要直接对每个 UID `asyncio.gather` 请求 Bilibili card 接口。头像 URL 每 24 小时刷新一次；聊天卡片渲染会再把头像图片本体缓存到 `plugin_data/astrbot_plugin_bilibili_push/image_cache/avatars/`。
- Cookie 账号池长期数据存 SQLite，运行时轮换、风控冷却和 SSL 配置集中在 `http.py`，新增接口请求应复用这套能力。
- 账号触发 `352/403/412` 风控后进入 `risk_cooldown_sec` 冷却，不应直接永久失效；冷却结束后会自动恢复参与轮换。
- HTTP `429`、`403/412` 或 Bili `352` 这类限频/风控不按普通网络错误重试；交给账号冷却、调用方降级或用户重新发起。
- 插件生命周期、资源初始化、临时文件清理和最终消息发送放 `runtime.py`，`main.py` 只负责装配和注册。
- `types.py` 是内部稳定契约。修改 `Post`、`SubUnit`、`MessageSegment` 时，需要同步 `scheduler/`、`utils/renderers/` 和模板字段。

## API 模型说明

- `models.py` 只保留字段结构和少量类级别短说明；字段语义放在本文档维护，避免模型文件变成接口注释手册。
- `model_rebuild_recurse()` 需要在模型类定义完成后调用，不能作为类装饰器使用；装饰器执行时嵌套类型和 forward reference 还没有完整进入命名空间。
- `UserAPI.Info.uname` 与 `UserAPI.Info.name` 分别对应不同 Bilibili 用户接口返回；`UserAPI.Data.info` 和 `card` 也是不同接口的载荷入口。
- `PostAPI` 参考 Bilibili 动态接口结构；`DYNAMIC_TYPE_NONE` 表示源动态已删除，常见于转发动态的原动态不可见。
- `PostAPI.Basic.rid_str` 在专栏动态中通常等于专栏 ID，在视频动态中通常等于 av 号。
- `PostAPI.Modules.Desc.rich_text_nodes` 保存动态正文富文本节点，解析正文、话题和跳转链接时由 `dynamic/post_parser.py` 处理。
- `PostAPI.Modules.Dynamic.major` 可能为空；正文动态、删除动态或部分转发动态不能假设一定存在主内容。
- `LiveRecommendMajor.LiveRecommand.content` 是 JSON 字符串，解析后才是直播推荐卡片结构。
- `LiveRecommendMajor.LivePlayInfo.uid` 是 UP 主 UID，不是直播间号；直播间号使用 `room_id`。
- Bilibili 返回的 `jump_url` 可能是 `//` 开头的相对协议链接，渲染或跳转前需要按调用场景补协议。
- 图片字段中的 `size` 使用 KiB；模板不依赖它，下载或筛选逻辑使用前需确认单位。
- `CommonMajor` 覆盖会员购、漫画、赛事、游戏中心、装扮等官方功能卡片，无法按普通视频/图文假设字段语义。

## 账号池说明

- `HttpClient._accounts` 是运行态账号池缓存，持久化来源是 SQLite `accounts` 表。
- 账号项包含 `uid`、`name`、`face`、`cookies`、`valid`，运行时还可能带 `status_code`、`cooldown_until`、`failure_count`。
- `add_account()` 和 `upsert_account()` 都按 UID 覆盖内存中的同账号信息，再同步 SQLite。
- `get_client()` 会在创建长期 `httpx.AsyncClient` 后加载账号池，并把当前可用账号 Cookie 注入客户端。
- 当前账号冷却或失效时只轮换一次；全部不可用时清空客户端 Cookie，让调用方按匿名请求或失败路径处理。
- `utils.py` 的 WBI 签名会按 Bilibili 规则排序参数、写入 `wts`，并过滤 `!'()*` 后计算 `w_rid`。
