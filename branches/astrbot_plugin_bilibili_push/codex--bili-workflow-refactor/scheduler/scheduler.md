# scheduler 模块

`scheduler` 是订阅推送的周期执行器。

## 文件职责

- `scheduler.py`: 读取订阅、分组轮询、动态去重、直播状态缓存、渲染并分发推送。
- `dynamic_checker.py`: 动态订阅检查和动态去重。
- `live_checker.py`: 直播订阅检查、直播状态缓存和手动直播检查。
- `dispatcher.py`: 分类过滤、主题选择、渲染和推送回调。
- `subscription_group.py`: 数据库订阅到 `SubUnit` 的分组转换。

## 维护说明

- 动态去重缓存使用 AstrBot KV，key 形如 `seen_posts_{uid}`。
- 直播状态缓存使用 AstrBot KV，key 形如 `live_status_{uid}`。
- 周期检查和手动直播检查只读取 `enabled=True` 的订阅。
- 新订阅首次动态检查只建立基线，不推送历史动态。
- 网络抓取失败不能更新去重基线。
- `scheduler.py` 是统合入口，不应重新堆入具体动态/直播检查逻辑。
- `scheduler.py` 按 `dynamic_check_interval` 和 `live_check_interval` 分别调度动态与直播，避免两类请求固定同一时刻打出。
- `dynamic_checker.py` 负责动态基线和新动态筛选，同一轮不同 UP 之间使用 `request_delay_sec` 做轻量限速。
- `live_checker.py` 负责周期直播检查和 WebUI 手动直播检查，直播状态使用 `batch_get_status()` 按 `live_batch_size` 批量查询。
- 直播批量检查遇到非风控异常时会拆分批次重试；明确风控错误不做单 UID 追打，避免放大请求压力。
- WebUI 的“全部直播检查”会先按 UID 去重，再批量查询状态并按订阅目标分发，避免多群重复请求同一 UP。
- `dispatcher.py` 是推送出口，新增主题、分类过滤或消息组件时在这里接入。
- `subscription_group.py` 是数据库订阅到轮询单元的转换层，修改订阅字段时需要同步这里。
