# handlers 模块

`handlers` 放用户入口适配层，避免 `main.py` 承载具体业务。这里的职责是把 AstrBot 命令、LLM tool、链接解析入口转换为内部服务或 workflow 调用。

## 文件职责

- `subscription_handler.py`: 订阅列表入口；显式增删命令已改由 `main.py` 构造 workflow。
- `subscription_editor.py`: 旧 UID 直连增删实现和变更卡片，仅保留给内部兼容路径；关键词输入应走 `workflows/subscription.py`。
- `subscription_list.py`: 订阅列表聚合、头像补全、直播状态补全和列表卡片。
- `search_handler.py`: 搜索命令薄适配层，统一转入 `workflows/search.py` 渲染候选卡。
- `ai_handler.py`: LLM tool 适配层，运行统一 workflow；不确定具体动作时可走 `ai_dispatch` 前置分流，工具结果默认留在后台给模型组织回复。
- `login_handler.py`: Bilibili 扫码登录和账号池状态展示。
- `link_handler.py`: 聊天消息里的 Bilibili 链接自动解析。

## 维护说明

- 新命令在 `main.py` 注册，具体业务放入对应 handler 或 `workflows/`。
- Handler 不直接做周期任务；周期行为放 `scheduler/`。
- 聊天侧需要卡片展示时，优先复用 `workflows/presenter.py` 或现有模板，不要在 handler 内重写渲染协议。
- `search_handler.py` 只做命令到 workflow 的适配，不再保留独立 Bilibili 搜索实现。
- 添加/删除订阅命令也只做命令到 workflow 的适配；不要重新调用旧 UID 直连编辑器处理关键词。
- `ai_handler.py` 返回给模型的是 `WorkflowResult.text`；工具调用默认后台处理，不主动渲染 HTML 图片卡片。只有参数显式包含 `present`、`foreground` 或 `show_card` 时，才把 `WorkflowResult.cards` 发到用户侧。
- `link_handler.py` 可以在配置开启时为视频解析追加视频附件；下载失败或超过大小限制时必须只保留解析卡片。
- 最终写入或删除订阅仍由 workflow pending 确认控制，AI 工具不得绕过确认直接替用户修改订阅。
- Web 管理 API 不放在普通 handler 中，避免聊天入口与 Plugin Pages 管理入口耦合。
- 登录账号状态涉及 Cookie 敏感信息，输出必须过滤 Cookie，只展示账号和有效性状态。
