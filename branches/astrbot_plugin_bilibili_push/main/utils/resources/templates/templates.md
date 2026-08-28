# templates 模块

`utils/resources/templates` 放所有图片卡片 HTML 模板。

## 模板职责

- `sub_add.html.jinja`: 添加和删除订阅结果卡片。
- `sub_list.html.jinja`: 订阅列表和登录账号状态复用卡片。
- `workflow_candidates.html.jinja`: workflow 搜索候选卡片，提示用户引用消息回复序号。
- `workflow_confirm.html.jinja`: workflow 订阅最终确认卡片，提示用户引用消息确认/取消。
- `parser_bili.html.jinja`: 链接解析卡片。
- `movie_card.html.jinja`: 直播卡片。
- `dynamic_movie_card.html.jinja`: 动态推送卡片。

## 维护说明

- 当前模板按 Playwright 渲染能力设计，使用了 flex/grid/filter 等浏览器 CSS。
- 渲染器只等待 `DOMContentLoaded`，再用有界超时等待字体、网络空闲和图片完成；模板不要引入 Google Fonts 等生产环境可能长期阻塞的外部资源。
- 模板字体通过 `internal_font_face_css` 和 `internal_font_family` 注入，具体字体文件维护在 `utils/resources/fonts/`。
- 推送模板不要直接假设主图一定是原始 URL；主题渲染前可能已把直播封面或动态 hero 压缩为 data URI。
- 模板头像兜底必须使用 `default_avatar_data_uri`，不要在 `onerror` 中写远程 noface 或 favicon URL。
- `sub_list.html.jinja` 是透明多卡片模板，用于订阅列表、搜索结果和登录账号状态；不要再加整页背景图。
- workflow 专用模板只承载聊天展示提示；真实写库仍由 `workflows/` pending 确认流程控制。
- workflow 模板不显示 task id，后台通过不可见 marker 和引用消息定位 pending task。
- 如果引入轻量 HTML 渲染器，应单独维护 lite 模板，避免直接复用这些模板。
- 模板字段来源分散在 `handlers/`、`workflows/cards.py`、`utils/renderers/` 和 `parser/`，改字段时需要同步调用方。
- 推送动态和直播模板保留原 HTML 风格；订阅列表、账号状态和 workflow 卡片默认透明背景。
- `dynamic_movie_card.html.jinja` 的首图只作为顶部 hero 使用，不再重复进入正文图片网格；纯文字动态没有 cover 时不渲染顶部 hero。
- 新增模板时提供明确 selector，避免截图裁剪到整页空白。

## 预览

- 开发预览使用 `scripts/generate_template_previews.py`，输出目录建议放在 `template_previews/` 下，不纳入 WebUI。
- 预览脚本使用 Bilibili 热门数据和本地生成兜底图，目标是检查透明底、多卡片布局、workflow 候选和确认卡片是否可读。
- WebUI 管理页不提供模板预览功能；模板不确定性留在开发脚本和人工最终检查中处理。
