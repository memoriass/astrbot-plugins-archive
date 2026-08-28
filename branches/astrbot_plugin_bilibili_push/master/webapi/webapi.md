# webapi 模块

`webapi` 负责 AstrBot Plugin Pages 使用的后端接口。它只做请求解析、响应封装和服务委托，不承载聊天 workflow 业务。

## 文件职责

- `manager_api.py`: 注册管理页 API，并把路由委托给 CRUD / overview 服务。
- `manager_crud.py`: 订阅和账号的新增、编辑、删除、启停。
- `manager_login.py`: Bilibili Web 扫码登录二维码生成、轮询和账号池写入。
- `manager_overview.py`: overview 汇总、头像补全、直播状态补全和运行统计。
- `manager_serializers.py`: 输出序列化、分类、标签 / Cookie 解析和 Bilibili 用户信息查询。
- `manager_response.py`: 统一 `ok / error` 响应结构。
- `__init__.py`: 对外暴露 `register_bilibili_web_apis()`。

## 路由

插件前缀固定为 `astrbot_plugin_bilibili_push`，由 AstrBot Dashboard 转发到 `/api/plug/<plugin>/<endpoint>`。

- `GET overview`: 返回订阅、账号、目标会话、pending task 和运行统计。
- `POST subscriptions/create`: 新增订阅。
- `POST subscriptions/update`: 按原始 `uid + sub_type + target_id` 更新订阅。
- `POST subscriptions/enabled`: 按 `uid + sub_type + target_id` 启停订阅。
- `POST subscriptions/delete`: 按 `uid + sub_type + target_id` 删除订阅。
- `POST bilibili/user`: 按 UID 查询 Bilibili 昵称和头像，用于 WebUI 新增订阅前确认对象。
- `POST accounts/upsert`: 新增或编辑账号。
- `POST accounts/delete`: 按 UID 删除账号。
- `POST accounts/valid`: 按 UID 标记账号有效 / 失效。
- `POST accounts/qr/start`: 获取 Bilibili 扫码登录二维码。
- `POST accounts/qr/poll`: 轮询二维码登录状态，成功后写入账号池。
- `POST checks/live`: 手动直播检查。
- `POST pending/clear`: 清空 pending task。

## 订阅编辑约定

- 后端仍以单条订阅记录为单位。
- 前端编辑弹窗现在允许同时勾选动态和直播。
- 保存时前端会按类型分别调用 `subscriptions/create` 或 `subscriptions/update`。
- 这意味着一个 UID 在同一会话下可同时拥有动态和直播两条订阅记录。
- 删除仍按单条记录删除，不会因为编辑弹窗的双选行为自动删掉未提交的另一类型记录。
- `target_id` 必须是完整 AstrBot 会话标识，格式通常为 `平台实例:消息类型:会话 ID`，例如 `aiocqhttp:GroupMessage:374274729`。
- WebUI 新增订阅会把用户选择的实例、群/个人类型和号码组装成完整 `target_id`，后端不保存裸 QQ 群号或个人 ID。

## 维护说明

- `main.py` 只做注册，不写接口业务。
- 返回值统一用普通 `dict`，避免给插件增加额外 Web 依赖。
- POST 解析 JSON 时在函数内部处理，别提前把 `quart.request` 传播到更高层。
- 账号输出必须过滤敏感 Cookie。
- 扫码登录接口只返回二维码、状态和账号摘要，不返回 Cookie。
- 新增 endpoint 时，同时同步 `pages/manager/api.js`、`scripts/check_workflow_integration.py` 和本文件。
- 序列化字段统一放在 `manager_serializers.py`，避免前端适配多个后端形态。
