# Workflow Architecture

订阅工作流编排层。这里把自然语言、命令和 Agent 工具参数转换成具体 ANI-RSS 操作。

## 文件

- `models.py`: workflow 定义、别名、确认/取消回复集合。
- `branches.py`: AI 前置分流候选、上下文门禁、置信度和选择规则。
- `natural_text.py`: 中文自然语言清洗、番名/RSS URL/季度/评分参数抽取。
- `dispatch.py`: `ai_dispatch` 前置 workflow，把自然语言或不完整工具参数转入具体业务 workflow。
- `parsing.py`: workflow request 解析统合入口。
- `parsing_tool.py`: LLM tool 参数解析。
- `parsing_command.py`: 显式命令和短任务命令解析。
- `parsing_natural.py`: 中文自然语言意图解析。
- `runner.py`: workflow 分发入口，保持轻量，不承载具体业务步骤。
- `runtime.py`: 回复封装、卡片交互回复、静默连通性预检、订阅参数构造。
- `rss.py`: RSS 直连添加、确认添加、订阅预览。
- `mikan_flow.py`: Mikan workflow 统合入口，只重新导出各子流程。
- `mikan_add.py`: Mikan 按番名添加入口。
- `mikan_recommend.py`: Mikan 推荐候选流程。
- `mikan_search.py`: Mikan 搜索和字幕组 RSS 查询。
- `mikan_selection.py`: 番剧选择、字幕组选择和续跑自动添加。
- `mikan_fetch.py`: Mikan 搜索和字幕组查询缓存适配。
- `duplicates.py`: 写入 ANI-RSS 前的已启用订阅重复检查。
- `continuation.py`: 挂起任务续跑分发。
- `manage.py`: 订阅列表、单个刷新、全部刷新、连通性诊断。
- `pending.py`: 挂起任务、任务 ID 匹配、引用消息解析、继续流程辅助。
- `mikan.py`: Mikan 候选提取、补充 Bangumi 元数据、候选排序。
- `formatting.py`: 文本和卡片模板数据格式化。
- `utils.py`: 通用解析、类型转换、评分/季度格式化工具。

## 用户可见流程

- `ai_dispatch`: 自然语言前置分流，按上下文和置信度选择后续 workflow。
- `add_mikan_subscription`: 搜索 Mikan，选择番剧和字幕组后添加。
- `recommend_mikan_subscription`: 推荐候选番剧，选择番剧和字幕组后添加。
- `search_mikan`: 搜索 Mikan 或查看字幕组 RSS。
- `add_subscription`: RSS 直连预览，确认后添加。
- `continue_pending`: 继续挂起任务。
- `list_subscriptions`: 查看 ANI-RSS 已启用订阅。
- `refresh_subscription`: 刷新单个订阅。
- `refresh_all`: 刷新全部订阅。

诊断流程：

- `check_status`: 检查 ANI-RSS API 连通性，并输出 SQLite、挂起任务、缓存和渲染器状态。
- `preview_subscription`: 只预览订阅结构，不写入。

## AI 前置分流

借鉴 Bilibili push 的受控分支思路，自然语言和泛化工具参数不会直接落到业务 handler，
而是先进入 `ai_dispatch`：

- `branches.py` 只负责生成候选分支和置信度，不执行 API 写入。
- `dispatch.py` 只选择一个明确分支并转交给已注册 handler。
- 低置信度或多个候选差距过小时会返回可选分支，避免误触发添加、刷新等真实操作。
- 泛化的 Agent 参数，例如 `workflow=workflow` 或 `workflow=ai_dispatch`，会用 `text/query/target`
  中的自然语言重新分流。
- AI tool 内部调用交互型候选流程时默认只返回文本摘要和 task_id 给模型，不主动向用户发送候选卡或确认卡；
  传 `interactive=true` 或从显式命令入口进入时才展示前台卡片。

## 偏好学习

字幕组和语言是强结构化偏好，当前使用 SQLite 计数和近因数据，不引入向量库：

- 成功添加 Mikan 字幕组后记录当前会话的字幕组 label 和语言标签。
- `preference_mode=rank` 时只重排字幕组候选，不跳过用户选择。
- `preference_mode=auto` 时，只有同一字幕组达到 `preference_min_uses` 且领先候选足够明确，才会自动选择并添加。
- 当用户没有选择排在前面的偏好候选时，会给这些候选记录负反馈。
- 偏好排序同时考虑正反馈、负反馈和近因衰减；过旧数据会在清理任务中回收。

## 工具结果记忆

借鉴 Plana/Livememory 的 `tool_result` 思路，workflow 执行完会记录一条结果：

- 记录 `workflow`、`target`、调用来源、成功/失败判断、文本摘要和渲染卡片路径。
- `ai_dispatch` 分流后记录的是实际业务 workflow，不记录空泛的分流入口。
- 结果用于诊断和后续智能调用优化，不参与当前主流程的向量召回。

## 挂起任务 ID

任务 ID 使用 `ani` + 8 位 hex，例如 `anif237a38d`。

用户可输入完整 ID，也可输入当前会话不冲突的前几位或后几位，但必须保留 `ani` 前缀：

```text
/anif237a38d 1
/anif237 1
/ania38d 1
```

不支持旧格式 `ani-xxxx`、裸短码 `68d2`、`继续anixxxx`。
