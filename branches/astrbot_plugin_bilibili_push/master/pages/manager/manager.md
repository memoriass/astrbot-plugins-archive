# manager 页面

`pages/manager` 是 AstrBot Plugin Pages 的管理面板，负责展示和编辑 Bilibili Push 的概览、订阅、账号和待处理任务。

## 文件职责

- `index.html`: 页面入口和样式挂载。
- `app.js`: 页面状态、分页、弹窗和 API 调用。
- `api.js`: Plugin Pages bridge 封装。
- `account_qr.js`: 账号扫码登录弹窗状态和轮询控制。
- `overview.js`: 概览面板。
- `subscriptions.js`: 订阅卡片和编辑弹窗。
- `target_binding.js`: 订阅绑定目标的显示、解析和新增表单片段。
- `subscription_identity.js`: 新增订阅时的 UID 搜索和昵称、头像回填。
- `accounts.js`: 账号卡片和编辑弹窗。
- `pending_text.js`: 待处理任务文案。
- `renderers.js`: 各面板统一渲染入口。
- `utils.js`: HTML 转义、图标和通用 UI 片段。
- `mock_bridge.js`: 本地预览 fallback 数据。
- `style.css`: 全局主题和弹窗样式。
- `layout.css`: 页面结构、侧栏和顶部布局。
- `flora.css`: 背景装饰图层。
- `overview.css`: 概览布局。
- `subscriptions.css`: 订阅卡片、编辑弹窗和分页样式。
- `accounts.css`: 账号卡片和编辑弹窗样式。

## 当前行为

- 概览页只负责状态总览和运行能力，不承载模板预览。
- 订阅页保留分页；同一 UID、同一会话的动态和直播订阅合并为一张卡片，用双角标展示类型。
- 订阅编辑弹窗支持动态/直播双选，且会分别显示对应通知类别。
- 订阅卡片在 UP 主名称下方显示短目标，例如 `QQ群 374274729`；弹窗左侧显示绑定实例、目标类型和会话号码。
- WebUI 新增订阅时需要选择绑定实例、群/个人目标类型并填写群号或个人 ID，前端会组装成完整 AstrBot `target_id` 后提交。
- WebUI 新增订阅可填写 UID 后搜索 Bilibili 用户信息，用昵称和头像确认订阅对象。
- 账号页支持 Cookie 新增和扫码登录；扫码登录通过 WebAPI 获取二维码并轮询，成功后写入账号池。
- 账号卡片和订阅卡片都使用右上角齿轮和垃圾桶作为编辑 / 删除入口。
- 编辑已有订阅时，UID 和 UP 主信息不再占用输入位，只调整类型、类别、标签和启用状态。
- 模板预览功能已取消。

## 维护说明

- 页面只调用 `webapi/`，不直接访问数据库。
- 卡片类变更优先改 `subscriptions.js`、`accounts.js` 和对应 CSS。
- 绑定目标相关格式化优先改 `target_binding.js`；不要在订阅卡片里手写 `target_id` 解析。
- UID 搜索回填优先改 `subscription_identity.js`，后端用户信息查询走 `bilibili/user`。
- 扫码登录状态控制优先改 `account_qr.js`；登录接口细节放在 `webapi/manager_login.py`。
- 版本戳要同步更新，否则 Plugin Pages 会继续加载旧脚本。
- 新增页面功能时先确认是否需要落到 `workflow`，不要把聊天侧逻辑搬到 WebUI。
- 多类型订阅在页面侧拆成多条订阅记录提交，后端仍按单条订阅管理；列表展示层负责把同 UID、同会话的记录聚合为单张卡片。
- 当前没有做跨群聚合；每张订阅卡仍代表同一 UID 在同一个 `target_id` 下的订阅集合。
