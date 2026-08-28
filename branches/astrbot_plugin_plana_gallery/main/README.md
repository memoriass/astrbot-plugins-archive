# Plana Gallery

Plana Gallery 是 Plana 插件族的本地语境图库。它继续保留原有图片文件、SHA-256 身份、标题、caption、来源和实际内容标签，并在其上增加情绪、语气、场景、审核状态、聊天候选和反馈；Plana Core 通过受控 Service 或专用 loopback HTTP 请求已审核候选，不直接读取 Gallery SQLite。

## 主要能力

- 图片、目录、ZIP、公开 URL 本地化导入。
- SHA-256 去重和稳定 `gallery:<hash-prefix>` 引用。
- `needs-review` 待审核队列和批量人工打标。
- 面向用户的情绪、语气、场景和内容标签；强度按逐情绪 profile 管理，安全状态由后台单独维护。
- 标签别名、SQLite FTS5 和可解释候选排序。
- 只允许 `reviewed + safety:safe` 图片进入聊天候选。
- 候选 selected、delivered、skipped、negative、failed 事件记录。
- Vue 资产工作台：320/640px WebP 缩略图、组合标签筛选、真实分页、密度切换、批量审核/删除、详情抽屉和移动端布局。
- 单进程 SQLite 后台任务负责缩略图生成与恢复；原图和标签仍是事实源，缩略图可以重建。
- 图库、待审核、标签体系、检索诊断四入口 Web。

本插件不再接入或发布到 Lsky、Chevereto、Lychee 等外部图床。URL 导入仅用于把管理员指定的图片复制到本地事实源，运行时不依赖原 URL。

## 数据目录

AstrBot 插件数据目录中包含：

```text
astrbot_plugin_plana_gallery/
├─ gallery.sqlite3
├─ assets/
└─ gallery_settings.json
```

`gallery.sqlite3` 使用 WAL 和 busy timeout。图片文件、`gallery_assets`、规范标签、逐图情绪强度和审核记录是事实数据；FTS 索引可以删除后重建。当前 schema 版本为 v5。

## 标签约定

推荐每张生产图片至少包含：

```text
emotion:happy
emotion:speechless
tone:agree
scene:celebrate
intensity:2
safety:safe
```

一张图片可以同时属于多个 `emotion:*`。Web 会为每个情绪分别保存轻/中/强三级强度，并要求最多选择一个主情绪；例如“兴奋·强（主） + 无语·轻（次）”。逐情绪数据保存在 `gallery_asset_emotions`，不会通过 `emotion:excited-3` 一类组合标签扩张标签体系。旧 `intensity:1..3` 仍保留为兼容投影，值等于该图片所有情绪强度的最大值，因此旧筛选和旧客户端继续可用。

AI/VLM 的建议置信度与情绪强度是两个独立字段：置信度表示模型判断是否可靠，强度表示图片本身表达得有多强。AI 仍只能提出建议，必须人工确认后保存。

反应图库的默认情绪集合按使用场景分为：积极与亲近、意外与不确定、社交与自我意识、失落与对抗、低能量状态。核心规范标签约 20 项，覆盖开心、兴奋、觉得好笑、喜欢、感谢、得意、松口气、惊讶、困惑、无语、害羞、尴尬、难过、失望、生气、烦躁、害怕、紧张、嫌弃、疲惫和无聊。“关怀”继续保留，但视为安慰回应倾向，不作为事实型情绪判断。

未指定标签的导入项自动进入 `needs-review`。添加或修改标签不会自动通过审核；只有管理员明确执行“确认通过”后才移除 `needs-review` 并补充 `safety:safe`。需要限制的图片应显式标为 `safety:restricted`。

## Core 契约

同一 AstrBot 进程内，Core 优先从插件注册表获取 Gallery 的 `chat_service`，直接调用 candidates、resolve、feedback 和 status，不经过 AstrBot Dashboard HTTP，也不需要密钥。

只有 Gallery 与 Core 分进程运行时，才启用专用 loopback HTTP。默认服务前缀：

```text
http://127.0.0.1:6193/plana_gallery
```

Gallery 配置 `core_service_http_enabled=true` 并设置 `core_service_key`；Core 设置相同的 `plana_core_service_key`，请求头固定为 `X-Plana-Core-Key`。服务只绑定 `127.0.0.1`，默认关闭，不复用 AstrBot Dashboard JWT、Gallery `api_token` 或 URL query token。`/api/plug/plana_gallery/*` 仍用于 Dashboard 管理，不作为 Core 互访后备。

聊天接口：

- `POST /api/chat/candidates`：版本 `plana.gallery.candidates.v1`，返回受控候选和分数拆解。
- `GET /api/chat/resolve?asset_ref=...`：解析已审核本地文件路径。
- `POST /api/chat/feedback`：版本 `plana.gallery.feedback.v1`，幂等记录选择和投递事件。

候选请求可增量携带多个结构化情绪目标：`emotion_tag`、`target_intensity`、`prominence` 和 `weight`。主次由显式 `prominence` 决定，不依赖数组位置；未携带 `emotions` 的旧客户端继续使用 facets 行为。

候选排序同时计算情绪覆盖、逐项强度匹配、主情绪对齐和冲突惩罚。与主目标相反且强度为 3 的额外情绪会降权；弱次情绪或请求中明确包含的复合情绪不处罚。Core 只允许本机回环地址，模型只能从 API 返回的 `asset_ref` 中选择，也可以选择不发送图片。

Core feedback 不回传原始聊天正文；兼容 `query` 字段保持为空，只携带事件、稳定引用、选择方式和规范化情绪摘要。

## Web

Dashboard：

```text
/api/plug/plana_gallery/dashboard
```

- **资产整理**：按审核状态、来源和多个标签组合筛选；支持每页 24–96 张、页码跳转、批量选择、详情抽屉、本地路径和文件导入。
- **待审核**：先从现有标签分组中点选，再为每个已选情绪设置独立强度与主次；每个情绪提供轻/中/强对照示例，强冲突组合会提示人工确认；支持逐项接受 AI 建议、J/K、Space、Ctrl+S 和 Ctrl+Enter。
- **标签体系**：按稳定键、中文名称、说明和别名搜索；集中维护正式情绪、语气、场景和内容标签，不在管理界面展示测试覆盖数据。
- **检索诊断**：输入多个目标情绪及各自强度、主次，使用与 Core 相同的结构化请求查看真实缩略图、情绪覆盖/强度匹配/主情绪对齐/冲突惩罚、排除原因、强规则/模型建议、反馈按钮和后台任务状态。

API Token 仅保存在当前页面内存，不使用 `localStorage`。

审核保存使用单事务提交，保存标签与审核通过仍是两个明确动作。标签选择器优先展示可读名称，并支持说明和别名搜索；创建自由标签前会检查同名/同义项并要求二次确认。别名不能静默占用其他标签定义或已有别名。缩略图缺失或过期时后台重新生成，页面显示占位状态且不会阻塞管理 API。

## 命令

启用 `enable_commands` 后：

```text
/图库
/图库 搜索 <关键词>
/图库 随机 [标签或关键词]
/图库 发送 <id|asset_ref|关键词>
/图库 收图 [标签]
/图库 导入 <本地路径> [tags=...]
/图库 删除 <id|asset_ref> confirm
/图库 统计
```

导入、收图和删除受管理员权限与确认边界保护。

## 配置

- `enabled`
- `api_token`
- `max_import_bytes`
- `allow_original_path`
- `enable_commands`
- `allow_chat_image_import`
- `upload_wait_seconds`
- `chat_download_timeout_seconds`
- `enable_silent_chat_image_collection`：默认关闭；开启后静默采集群聊图片，不回复也不拦截原消息。
- `silent_collection_scope_allowlist`：逗号分隔群号或 unified message origin；留空表示所有群聊。
- `silent_collection_daily_limit_per_scope` / `silent_collection_global_daily_limit`：滚动 24 小时新增配额。
- `silent_collection_max_images_per_message` / `silent_collection_max_bytes`：单消息和单图资源限制。
- `silent_collection_max_pixels` / `silent_collection_max_gif_frames`：解码安全限制。
- `tagging_ai_enabled`
- `tagging_ai_provider`
- `tagging_confidence_threshold`

AI/VLM 只能生成打标建议，不能自动解除 `needs-review`。

静默采集只处理已确认的群聊图片。图片优先读取适配器本地缓存，否则仅通过正常 TLS 的 HTTP(S) 下载；不降级为明文 HTTP。采集记录仅保存会话、发送者和消息标识的 SHA-256，不保存聊天正文、QQ 号或原始 URL。新图片使用 `source=chat-silent` 并进入 `needs-review`；重复图片只记录观察事件，不改写原资产标签、来源和审核状态。

## 升级说明

旧版本的 `gallery_remote_assets` 表会保留一个兼容周期，供管理员审计或导出历史映射；新代码不再写入该表，也不会加载远端 provider。详见 `docs/local_gallery_migration.md`。

## 验证

```powershell
cd web/frontend
npm install
npm run test
npm run build
cd ../..
python -m compileall -q .
python scripts/check_gallery_beta.py
python scripts/benchmark_local_candidates.py
git diff --check
```

生产运行只读取已提交的 `web/dist/index.html`，不需要安装 Node.js。修改 Vue 源码后才需要重新执行前端构建。

本机迁移预览可使用 `python scripts/run_gallery_web_preview.py --database <gallery.sqlite3> --port 6198`。该服务以 SQLite 只读模式打开数据库，读取已有逐图情绪 profile，并投影 v5 标签定义和诊断兼容关系，不执行 schema 初始化或写操作。

旧标签归一先运行 `python scripts/govern_legacy_gallery_tags.py --database <gallery.sqlite3> --report <report.json>` 生成只读报告；确认后再增加 `--apply --backup-root <backup-dir>`。唯一明确目标会直接替换旧标签；已有人工情绪、语气或场景分类的素材会移除旧标签；仍无法判断的素材进入 `needs-review`，内容类自由标签按原义保留。

全库视觉情绪复核可使用 `python scripts/apply_gallery_visual_classification.py --database <gallery.sqlite3> --input <classification.json> --report <report.json>` 预览。正式写入必须增加 `--apply --backup-root <backup-dir>`；工具只替换 `emotion:*`、逐情绪强度和兼容 `intensity:*`，不会根据视觉模型自动分类角色，也不会删除原自由标签。

争议素材可按“快速、标准、审慎”顺序提供至少三份独立结果给 `python scripts/apply_gallery_consensus_review.py --database <gallery.sqlite3> --review <quick.json> --review <standard.json> --review <deliberate.json> --report <report.json>`。工具要求多数主情绪得到最后一份审慎复核支持，强度分歧不超过一级；正式写入同样需要 `--apply --backup-root <backup-dir>`，并始终保留 `needs-review`，不会自动审核通过。

完成多档复核后，可使用 `python scripts/finalize_gallery_review_queue.py --database <gallery.sqlite3> --classification <classification.json> --consensus <consensus.json> --report <report.json>` 预览最终人工队列。工具要求分类清单完整覆盖全库，并要求共识的已解决项与未解决项完整覆盖原人工复核集合；正式写入必须增加 `--apply --backup-root <backup-dir>`，且只增删 `needs-review`，不会改写图片、情绪 profile 或旧标签。

进入正式场景前，可使用 `python scripts/finalize_gallery_release_data.py --database <gallery.sqlite3> --assignments <emotion-assignments.json> --report <report.json>` 预览来源名归一、待审核安全状态修正和人工补标；跨系统迁移时增加 `--asset-root <assets-dir>`，工具会按 SHA-256 校验并修复本地资产路径。正式写入必须增加 `--apply --backup-root <backup-dir>`。工具会保存数据库备份、资产 SHA-256 清单和补标清单，并可重复执行。

正式标签体系在原有 22 类基础上增加期待、俏皮、平静、好奇、无奈、委屈、挫败、内疚和慌张。完成归一后，旧情绪标签不再并列展示；无法确定实际分类的图片统一进入待审核。

20,000 张基准只验证本地 SQLite/FTS 候选路径，不下载模型或访问外部服务。
