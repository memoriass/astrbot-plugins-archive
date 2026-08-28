# dynamic 模块

`dynamic` 负责 Bilibili 动态订阅链路。

## 文件职责

- `bilibili.py`: 平台类 `BilibiliDynamic`，负责接口请求、风控重试、入口方法。
- `fallback.py`: 旧动态接口卡片转换，把旧接口结构转换成 `PostAPI.Item`。
- `post_parser.py`: 动态类型分类、正文/图片抽取、转发内容构造、`Post` 输出。

## 数据流

1. `BilibiliScheduler` 调用 `BilibiliDynamic.fetch_new_post()`。
2. `bilibili.py` 优先请求 polymer 新接口。
3. 新接口失败或返回空时尝试旧接口。
4. 旧接口数据经 `fallback.py` 统一成新模型。
5. `post_parser.py` 把 `DynRawPost` 转成内部 `Post`。

## 维护说明

- 动态接口失败必须抛错或记录失败，不要返回假空列表。
- 新增动态类型时优先改 `post_parser.py` 的解析和分类。
- 旧接口转换只做兼容兜底，不要把主解析逻辑放回 `fallback.py`。
- `bilibili.py` 作为平台入口，不承载具体解析细节。
- `fetch_new_post()` 的调用方依赖“失败不更新基线”的语义；异常吞掉会导致调度器误认为没有新动态。
- `Post` 输出字段会进入推送主题模板，新增字段时同步 `utils/renderers/` 和 `utils/resources/templates/`。
- 接口字段变更时先调整 `core/models.py`，再处理本模块转换，避免在解析器里堆散装字典兼容。
