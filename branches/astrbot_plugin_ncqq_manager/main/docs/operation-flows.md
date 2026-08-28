# 核心操作流程

本文记录主要 workflow 的业务顺序。修改 `workflows/instance_flows.py` 或 `workflows/admin_flows.py` 时，应同步对应流程图。

## 创建实例

```mermaid
flowchart TD
    A["create_instance(target=name)"] --> B{"实例名是否明确"}
    B -- "否" --> B1["停止：要求补充实例名"]
    B -- "是" --> C["读取目标 manager 的 /api/containers"]
    C --> D{"实例是否已存在"}
    D -- "是" --> E{"当前用户是否有权限"}
    E -- "否" --> E1["停止：实例已存在但无权限"]
    E -- "是" --> F["跳过创建，继续创建后流程"]
    D -- "否" --> G{"触发者是否管理员"}
    G -- "否" --> G1["生成整合审批，保存 manager_id"]
    G1 --> G2["审批通过后执行：创建、绑定、可选接入后端"]
    G -- "是" --> H["调用 POST /api/containers"]
    H --> I["等待 create/start 事件并重新读取列表"]
    I --> J{"实例是否可见"}
    J -- "否" --> J1["停止：创建已提交，稍后继续重登或接入"]
    J -- "是" --> F
    F --> K{"是否需要绑定用户"}
    K -- "是" --> K1["写入 manager/instance 到 user_mapping"]
    K -- "否" --> L{"是否需要启动"}
    K1 --> L
    L -- "是且未运行" --> L1["调用 start"]
    L -- "否或已运行" --> M{"是否提供 backend_alias"}
    L1 --> M
    M -- "是" --> M1["接入目标 manager 的已有后端"]
    M -- "否" --> N["刷新登录状态"]
    M1 --> N
    N --> O{"是否已登录"}
    O -- "是" --> O1["结束：返回在线账号"]
    O -- "否且 qrcode=true" --> P["拉取二维码"]
    O -- "否且 qrcode=false" --> P1["结束：提示未登录"]
```

推荐参数：

```json
{
  "backend_alias": "astrbot",
  "bind_qq": "123456",
  "nickname": "可选昵称",
  "qrcode": true,
  "auto_start": true
}
```

## 掉线重登

```mermaid
flowchart TD
    A["relogin_instance(target=name)"] --> B{"能否解析目标实例"}
    B -- "否" --> B1["停止：要求指定实例"]
    B -- "是" --> C{"是否有 manager/instance 权限"}
    C -- "否" --> C1["停止：无权操作"]
    C -- "是" --> D{"restart_first=true"}
    D -- "是" --> D1["先调用 restart"]
    D -- "否" --> E["刷新登录状态"]
    D1 --> E
    E --> F{"已登录"}
    F -- "是且非 force_qrcode" --> F1["结束：返回在线账号"]
    F -- "否" --> G{"qrcode=true 或 force_qrcode=true"}
    G -- "是" --> G1["拉取二维码"]
    G -- "否" --> G2["结束：只报告离线状态"]
```

## 实例诊断

```mermaid
flowchart TD
    A["check_instance(target=name)"] --> B["读取目标 manager 容器列表"]
    B --> C{"实例是否存在"}
    C -- "否" --> C1["停止：实例不存在"]
    C -- "是" --> D["刷新登录状态"]
    D --> E["读取资源监控"]
    E --> F["读取最近日志"]
    F --> G{"是否指定 path/file_name"}
    G -- "是" --> H["读取文件树或配置摘要"]
    G -- "否" --> I["输出检测结果"]
    H --> I
```

## 综合健康检查

```mermaid
flowchart TD
    A["内部健康聚合"] --> B["并发读取目标 manager 健康子项"]
    B --> C["/api/health"]
    B --> D["BotShepherd status / activation / heartbeat"]
    B --> E["/api/bots"]
    B --> F["/api/containers"]
    B --> G["后端端点列表"]
    C --> H["汇总 manager 状态"]
    D --> I["汇总 BotShepherd 状态"]
    E --> J["汇总 Bot 在线数"]
    F --> K["汇总实例运行数"]
    G --> L["汇总后端端点数"]
    H --> M{"是否 details=true"}
    I --> M
    J --> M
    K --> M
    L --> M
    M -- "否" --> N["输出一屏健康摘要"]
    M -- "是" --> O["摘要后追加细分诊断详情"]
```

## 定时掉线检测

```mermaid
flowchart TD
    A["cron 触发 do_health_check"] --> B["遍历所有 manager"]
    B --> C["读取每个 manager 的实例列表"]
    C --> D["生成 manager/instance 在线快照"]
    D --> E["与上一轮 health_snapshot 比较"]
    E --> F{"是否有掉线或恢复"}
    F -- "否" --> F1["结束"]
    F -- "是" --> G["按 manager/instance 查找 owner"]
    G --> H["私聊 owner"]
    G --> I{"是否配置 notify_group"}
    I -- "是" --> J["发送群告警卡片"]
    I -- "否" --> K["只做私聊通知"]
```

## ncqq-manager 掉线 POST 通知

```mermaid
flowchart TD
    A["ncqq-manager plugin_api 规则 POST"] --> B["core/offline_webhook.py 独立接收器"]
    B --> C{"token 是否有效"}
    C -- "否" --> C1["返回 401"]
    C -- "是" --> D["解析 event / instance / manager"]
    D --> E{"event 类型"}
    E -- "login_lost 或 instance_offline" --> F["写入 health_snapshot=false"]
    E -- "instance_online 等恢复事件" --> G["写入 health_snapshot=true"]
    F --> H{"是否为新状态边沿"}
    G --> H
    H -- "否" --> H1["返回 ok，不重复通知"]
    H -- "是" --> I["复用 health_check 通知函数"]
    I --> J["私聊 owner"]
    I --> K{"是否配置 notify_group"}
    K -- "是" --> L["发送群告警卡片"]
    K -- "否" --> M["结束"]
```

该 HTTP 接收器不注册为 LLM 工具，也不注册为 Plugin Pages API。它只用于 ncqq-manager 的机器对机器 POST 回调；内部状态仍落到 `health_snapshot`，与定时轮询共享去重边界。
