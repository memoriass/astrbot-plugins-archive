# core 模块

`core` 放跨模块共享能力，不包含具体命令和推送业务。

## 文件职责

- `types.py`: 插件内部标准类型，如 `Post`、`SubUnit`、`MessageSegment`。
- `models.py`: Bilibili API 的 Pydantic 模型。
- `http.py`: 全局 `httpx.AsyncClient`、SQLite 账号池读取、风控账号轮换。
- `platform.py`: 动态平台和状态平台的抽象基类。
- `config.py`: 插件配置解析和安全兜底。
- `compat.py`: Pydantic v1/v2 兼容入口。
- `runtime.py`: 插件运行期资源初始化、临时文件清理和最终消息发送。
- `utils.py`: 通用算法和 Bilibili WBI 签名。

## 维护说明

- Bilibili API 响应字段变化时，优先更新 `models.py`，再调整 `dynamic/`、`live/` 或 `parser/` 的转换逻辑。
- 任何跨 Pydantic v1/v2 的调用都应通过 `compat.py`，避免业务模块直接依赖版本差异。
- 插件启动配置统一通过 `config.py` 解析；新增配置项时同步 `_conf_schema.json`、`README.md` 和 `main.py` 装配字段。
- 长期 HTTP client 统一走 `HttpClient.get_client()`；新增网络访问时不要在 handler 或 workflow 中创建全局 client。
- Cookie 账号池长期数据存 SQLite，运行时轮换、风控冷却和 SSL 配置集中在 `http.py`，新增接口请求应复用这套能力。
- 账号触发 `352/403/412` 风控后进入 `risk_cooldown_sec` 冷却，不应直接永久失效；冷却结束后会自动恢复参与轮换。
- 插件生命周期、资源初始化、临时文件清理和最终消息发送放 `runtime.py`，`main.py` 只负责装配和注册。
- `types.py` 是内部稳定契约。修改 `Post`、`SubUnit`、`MessageSegment` 时，需要同步 `scheduler/`、`utils/renderers/` 和模板字段。
