# Plana Core

Plana Core 是 AstrBot 内部的 Plana 备份 OS 运行时插件。

## 定位

- Plana：工具执行、内网管理、任务记录、风险检查。
- 阿罗娜：主 OS、情感陪伴、关系主记忆。
- Plana Core 不替代阿罗娜进行情感陪伴。

## 当前能力

- 记录用户 identity 与 session stream。
- 使用 SQLite 保存 Plana 状态、事件记忆、语义记忆与关系边。
- 在 LLM 请求前注入带字符预算与优先级裁剪的 Plana prompt block。
- 在 LLM 响应后写入简单 episode。
- 使用 memory activator 激活事件记忆、事实记忆与关系图谱，支持概念图扩散式激活检索。
- 使用 memory consolidator 将事件记忆沉淀为事实记忆。
- 使用 memory decay 对普通事件记忆执行批量衰减，保留授权、风险与显式事实；高权重概念关联的记忆衰减更慢。
- 使用 task queue / rule planner 管理任务目标、风险级别、规划步骤与任务结果摘要。
- 可选 LLM 概念关键词提取，随对话自动积累概念图（默认关闭）。
- 概念图记忆整合：概念已存在时使用 LLM 融合新旧记忆片段。
- 相似概念自动合并：新概念与已有概念 cosine 相似度 ≥ 0.7 时自动合并（jieba 分词 + token-set cosine）。
- 两阶段 LLM 记忆筛选：概念注入前先扩散激活候选，再由 LLM 筛选相关概念（随机 ID 消除位置偏差）。
- LLM 结构化记忆抽取：从用户消息与回复中写入 `user_fact`、`user_preference`、`promise`、`task_fact`、`risk_event`、`relationship_note`。
- LLM 记忆检索规划：在 prompt 构建前生成 memory query，改善“上次/之前/那个”等指代场景召回。
- 工具结果记忆化：任务队列结果写入 `tool_result` / `task_fact` / `risk_event`。
- 消息→概念压缩：批量压缩历史记忆为概念图节点。
- 主动回忆工具：注册 `plana_recall_memory` LLM tool，按需召回长期记忆。
- RRF 融合检索：轻量融合情景记忆、语义画像与概念图路由，并返回 `score_breakdown` 解释。
- 内置 Web 管理面板（深色蔚蓝 Plana/备份 OS 风格，纯 HTML/CSS/JS，无外部素材依赖）。
- 后台自动维护（统一沉淀 + 衰减 + 概念积累）。
- 支持 jieba 分词（可选依赖），提升中文搜索质量；无 jieba 时回退为简单分词。
- 预留阿罗娜接口模型，但默认不启用。

## 命令

聊天命令精简为 6 个，管理功能迁移至内置 Web 面板：

```text
/plana              — 状态概览
/plana mode <mode>  — 切换模式 (standby/observing/tasking/checking/risk_review/waiting_confirm/reporting/handoff_to_arona/silent)
/plana search <q>   — 搜索记忆
/plana remember <f> — 记住事实
/plana task list|add|done|cancel
/plana help         — 显示帮助
```

## Web 管理面板

PlanaCore 提供两套 Web 入口：

| 入口 | URL | 认证配置 | 用途 |
|------|-----|----------|------|
| AstrBot 内嵌面板 | `http://<astrbot-host>:6185/api/plug/plana/dashboard` | `ops_bridge.debug_api_token` | 跟随 AstrBot 主 Dashboard 运行。 |
| 独立管理端 | `http://127.0.0.1:6180/` | `standalone_web.web_admin.password` | 独立 FastAPI/Uvicorn 服务，适合本机调试。 |

独立管理端启用后，根路径 `/` 与 `/dashboard` 均返回 Dashboard 页面，不再返回 `{"detail":"Not Found"}`。

功能：
- **概览** — 系统状态、功能开关、数据表统计、typed memory kind 列表
- **记忆** — 浏览/搜索记忆记录，支持 typed memory kind 下拉筛选
- **检索实验室** — 模拟记忆检索链路，展示 RRF 融合结果、情景记忆、语义画像、概念扩散、分数分解与 Prompt 上下文预览
- **画像** — 汇总 user semantic memory、偏好、承诺与 Plana 关系边
- **Bridge** — 展示 NachoBridge/Arona 协议状态、标准请求类型与调试说明
- **概念图** — 查看概念节点与边
- **关系** — 关系图数据
- **任务** — 任务列表
- **维护** — 手动触发沉淀/衰减/概念积累，查看 SQLite 校验、表计数、孤儿链接、备份列表，并支持创建备份与备份后重建索引

认证：
- 内嵌面板：若配置 `ops_bridge.debug_api_token`，需在 URL 加 `?token=xxx` 或请求头 `X-Plana-Token` / `Authorization: Bearer ...`。
- 独立管理端：若配置 `standalone_web.web_admin.password`，页面会显示登录框；登录成功后使用临时 Bearer token 调用 `/api/*`。

视觉：
- 页面采用深色蔚蓝、毛玻璃卡片、星点背景、菱形 Plana OS 标识与启动页 hero。
- 仅使用 CSS 渐变和 Unicode 几何符号，不依赖蔚蓝档案官方素材或外部图片。
- 独立 Web 与 AstrBot 内嵌面板共用同一 HTML 模板。

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plug/plana/dashboard` | 内嵌面板 HTML |
| GET | `/api/plug/plana/api/overview` | 内嵌面板综合概览 JSON |
| GET | `/api/plug/plana/api/memories?scope=global&limit=20&q=&kind=` | 内嵌面板记忆列表/按 kind 筛选 |
| GET | `/api/plug/plana/api/retrieve-test?scope=global&q=&kind=&limit=8` | 内嵌面板检索实验室 JSON |
| GET | `/api/plug/plana/api/context-preview?scope=global&q=&kind=&limit=8` | 内嵌面板 Prompt 上下文预览 JSON |
| GET | `/api/plug/plana/api/profile?scope=global&limit=20` | 内嵌面板画像 JSON |
| GET | `/api/plug/plana/api/bridge-status` | 内嵌面板 Bridge 状态 JSON |
| GET | `/api/plug/plana/api/maintenance-status` | 内嵌面板维护校验、表计数、备份列表 JSON |
| POST | `/api/plug/plana/api/backup` | 内嵌面板创建 SQLite 备份 |
| POST | `/api/plug/plana/api/rebuild-indexes` | 内嵌面板备份后重建查询索引 |
| POST | `/api/plug/plana/api/maintain` | 内嵌面板手动触发维护 |
| GET | `/` | 独立管理端 HTML |
| GET | `/dashboard` | 独立管理端 HTML |
| GET | `/api/overview` | 独立管理端综合概览 JSON |
| GET | `/api/memories?scope=global&limit=20&q=&kind=` | 独立管理端记忆列表/按 kind 筛选 |
| GET | `/api/retrieve-test?scope=global&q=&kind=&limit=8` | 独立管理端检索实验室 JSON |
| GET | `/api/context-preview?scope=global&q=&kind=&limit=8` | 独立管理端 Prompt 上下文预览 JSON |
| GET | `/api/profile?scope=global&limit=20` | 独立管理端画像 JSON |
| GET | `/api/bridge-status` | 独立管理端 Bridge 状态 JSON |
| GET | `/api/maintenance-status` | 独立管理端维护校验、表计数、备份列表 JSON |
| POST | `/api/backup` | 独立管理端创建 SQLite 备份 |
| POST | `/api/rebuild-indexes` | 独立管理端备份后重建查询索引 |
| POST | `/api/maintain` | 独立管理端手动触发维护 |

## 配置

配置界面按 AstrBot 插件配置文档的 object schema 分组展示，旧版平铺配置仍由运行时兼容读取；旧 `ops_bridge.enable_auto_maintenance` / `ops_bridge.auto_maintenance_interval_hours` 也会迁移读取。当前 schema 仅使用本地 Dashboard 已支持的 `description`、`hint`、`obvious_hint`、`default`、`options` 与 `object.items` 字段；LLM 成本项、token、全量记录、独立 Web 密码等敏感项带醒目提示。

| 分组 | 关键字段 | 说明 |
|------|----------|------|
| `core` | `enabled`, `mode`, `inject_prompt` | 基础运行、默认模式、Prompt 注入。 |
| `memory` | `record_messages`, `max_active_memories`, `max_prompt_chars`, `enable_memory_activation` | 消息记录与 Prompt 召回预算。 |
| `maintenance` | `enable_memory_consolidation`, `enable_memory_decay`, `enable_auto_maintenance`, `auto_maintenance_interval_hours` | 记忆沉淀、衰减与后台维护。 |
| `task_relation` | `enable_task_queue`, `task_list_limit`, `enable_relation_graph` | 任务队列与关系图。 |
| `life_memory` | `enable_concept_extraction`, `enable_structured_memory_extraction`, `enable_memory_query_planner`, `enable_recall_tool`, `recall_default_k`, `recall_max_k`, `recall_rrf_k`, `recall_include_semantic`, `recall_include_concept`, `accumulate_batch_size` | LLM 结构化长期记忆、概念图、检索规划、主动回忆工具与 RRF 融合参数。 |
| `ops_bridge` | `enable_web_dashboard`, `enable_debug_api`, `debug_api_token`, `enable_arona_api`, `arona_api_token` | 内嵌面板、调试 API、Nacho/Arona bridge。 |
| `persona_behavior` | `persona_style`, `record_all_messages`, `quiet_hours`, `mood_update_probability` | 人格覆盖、全量记录、免打扰与 mood 刷新。 |
| `standalone_web` | `web_admin.enabled`, `web_admin.host`, `web_admin.port`, `web_admin.password` | 独立 Web 管理端，默认端口 `6180`。 |

示例：

```text
core.enabled=true
core.mode=standby
memory.max_prompt_chars=4000
life_memory.enable_structured_memory_extraction=true
life_memory.enable_memory_query_planner=true
life_memory.enable_recall_tool=true
life_memory.recall_default_k=5
life_memory.recall_max_k=10
life_memory.recall_rrf_k=60
ops_bridge.enable_web_dashboard=true
ops_bridge.debug_api_token=
standalone_web.web_admin.enabled=false
standalone_web.web_admin.host=0.0.0.0
standalone_web.web_admin.port=6180
standalone_web.web_admin.password=
maintenance.enable_auto_maintenance=false
maintenance.auto_maintenance_interval_hours=6
```

`enable_concept_extraction=true`、`enable_structured_memory_extraction=true`、`enable_memory_query_planner=true` 均可能额外调用 LLM；可按成本关闭。`enable_recall_tool=true` 仅注册 LLM 工具与本地检索，不额外调用 LLM。

`maintenance.enable_auto_maintenance=true` 时启用后台自动维护，按 `maintenance.auto_maintenance_interval_hours` 间隔执行沉淀、衰减、概念积累。

## License

- SPDX: `AGPL-3.0-or-later`
- `metadata.yaml` 与 `LICENSE` 已按 AGPL-3.0-or-later 标注。



## LivingMemory 能力对照

面向 `astrbot_plugin_livingmemory` 的能力调研中，PlanaCore 按 `AGPL-3.0-or-later` 开源策略保留兼容设计；当前优先复用架构模式并保持 PlanaCore 自实现。

已落地能力：
- WebUI 管理面板从“只看数据”扩展为“检索实验室 + 画像 + Bridge 观测 + 上下文预览”。
- 检索解释化：展示情景记忆、语义记忆、概念扩散三条路径与命中数。
- 主动回忆工具：`plana_recall_memory` 已注册为 LLM tool，返回 JSON 化长期记忆结果。
- 轻量 RRF 融合：`PlanaRecallEngine` 融合 memory / semantic / concept 路由，并输出 `score_breakdown`。

- 维护可观测性：Web 维护页展示 SQLite `quick_check`、schema 表检查、孤儿链接检查、备份列表与数据库路径。
- 安全维护操作：提供 `maintenance-status`、`backup`、`rebuild-indexes` 双入口 API；重建索引前自动创建 SQLite 备份。

暂不纳入：
- Faiss/BM25 作为强依赖；当前 PlanaCore 先保留 SQLite + typed kind + concept graph 的轻量路径，RRF 只做本地排名融合。
- 完整替换 memory engine；PlanaCore 继续以“工具调用生命 + 长期记忆核心”为主，不转成单纯长记忆插件。
- 删除事务保护、危险操作二次确认与审计日志；后续作为安全写操作二期补齐。



## 阿罗娜接口策略

真实对接不放在本插件内。后续使用独立插件：

```text
astrbot_plugin_nacho_bridge
```

Plana Core 仅保留协议模型和可选 disabled API。默认：

```text
enable_arona_api=false
```

## 数据目录

```text
data/plugin_data/astrbot_plugin_plana_core/plana.sqlite3
```

## 详细计划

```text
docs/current/plan.md
docs/current/task.md
```


## 检查命令

```powershell
uv run ruff format data/plugins/astrbot_plugin_plana_core
uv run ruff check data/plugins/astrbot_plugin_plana_core
uv run python -m compileall -q data/plugins/astrbot_plugin_plana_core
uv run python -m py_compile data/plugins/astrbot_plugin_plana_core/main.py
uv run python -c "import json; json.load(open('data/plugins/astrbot_plugin_plana_core/_conf_schema.json', encoding='utf-8'))"
```

