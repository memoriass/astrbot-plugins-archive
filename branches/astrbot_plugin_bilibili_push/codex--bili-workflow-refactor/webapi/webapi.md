# webapi 模块

`webapi` 负责 AstrBot Plugin Pages 使用的后端接口。它只做 Web API 注册、请求解析、响应封装和服务委托，不承载聊天命令或 workflow 编排业务。

## 文件职责

- `manager_api.py`: 注册管理页 API，并把请求委托给对应服务。
- `manager_crud.py`: 订阅和账号的新增、编辑、删除、启停动作。
- `manager_overview.py`: overview 聚合、订阅头像补全、直播状态补全和运行统计。
- `manager_serializers.py`: 输出序列化、分类/标签/Cookie 解析和 Bilibili 用户信息查询。
- `manager_response.py`: Web API 请求读取和统一响应封装。
- `__init__.py`: 对外暴露 `register_bilibili_web_apis()`。

## 当前路由

路由前缀固定为 `/astrbot_plugin_bilibili_push/`，由 AstrBot Dashboard 转发为 `/api/plug/<plugin>/<endpoint>`。

- `GET overview`: 返回订阅、账号、目标会话、pending task 和运行统计；订阅会补全头像和直播状态，用于卡片展示。
- `POST subscriptions/create`: 新增订阅，支持 UID、类型、会话、分类、标签和启用状态。
- `POST subscriptions/update`: 按原始 `uid + sub_type + target_id` 定位并更新订阅字段。
- `POST subscriptions/enabled`: 按 `uid + sub_type + target_id` 启用或停用订阅。
- `POST subscriptions/delete`: 按 `uid + sub_type + target_id` 删除订阅。
- `POST accounts/upsert`: 新增或编辑账号；Cookie 只允许写入/替换，不从接口回显。
- `POST accounts/delete`: 按 UID 删除账号。
- `POST accounts/valid`: 按 UID 标记账号有效或失效。
- `POST checks/live`: 对指定会话执行手动直播检查；`target_id="__all__"` 时按全局唯一 UID 批量检查，再按订阅目标分发。
- `POST pending/clear`: 清空 workflow pending task。

## 维护说明

- `main.py` 只调用注册函数，不写具体接口逻辑。
- 接口返回普通 `dict`，避免给插件增加新的顶层 Web 依赖。
- POST 读取 JSON 时在函数内部惰性导入 `quart.request`。
- 账号输出必须过滤 cookies 等敏感字段。
- 写操作必须参数完整，不做模糊匹配。
- 账号编辑时 Cookie 为空表示保留原 Cookie，新增账号必须提供 Cookie。
- 手动直播检查会触发实际消息推送，页面侧必须显式确认。
- 管理 API 不提供模板预览、模板渲染或预览生成能力；模板渲染测试保留在开发脚本层。
- Web API 路由前缀必须与 `metadata.yaml` 的 `name` 和 `main.py` 注册名一致，当前为 `astrbot_plugin_bilibili_push`。AstrBot Plugin Pages bridge 会按插件名拼接 `/api/plug/<pluginName>/<endpoint>`。
- 新增 endpoint 时同步 `pages/manager/api.js`、`scripts/check_workflow_integration.py` 和本文件的路由列表。
- 输出字段应由 `manager_serializers.py` 统一整理，避免前端适配多个后端形状。
- 写接口必须返回明确 `ok/message/data` 结构，前端弹窗和 toast 依赖这些字段。
