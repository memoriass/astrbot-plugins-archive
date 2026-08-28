# P44 Web React 风格落地计划书

## 目标

把 Plana Core Web 从当前单页调试面板推进为现代化管理控制台骨架。第一阶段必须保持 AstrBot 插件可直接使用：无需 npm build、无需外部 CDN、嵌入 Dashboard 和独立 FastAPI Web 继续共用同一个页面入口。

视觉参考 `C:\git\ncqq-manager\frontend\src\layouts\AdminLayout.tsx`：

- 常驻左侧侧栏。
- 顶部工具栏。
- 明暗主题切换。
- 管理后台式密集信息布局。
- MUI 风格的导航、surface、chip、table 和 action button。

## 技术判断

1. 当前最稳妥方案是“React 风格无构建骨架”：
   - 保持 `web/page.py` 返回完整 HTML。
   - 使用组件化 JS helper 模拟 React component 组织方式。
   - 使用 CSS variables 做 theme token。
   - 不依赖 CDN，保证 AstrBot 插件部署即用。
2. 暂不直接引入 Vite/React/MUI：
   - AstrBot 插件当前没有前端构建流程。
   - 引入 npm 依赖会增加安装、构建和分发复杂度。
   - 后续可在 `web/frontend/` 新增 React 源码，并把构建产物嵌回 `page.py` 或静态文件服务。

## 分阶段计划

### P44-01 计划与参考审计

- 审计当前 `web/page.py` 和 `web/dashboard_shell.md`。
- 读取 ncqq-manager 的 `AdminLayout.tsx`、主题切换和 package 依赖。
- 固化本计划书。
- 验收：计划书存在，当前仓库工作区清晰。

### P44-02 AstrBot 可用 Web Shell 骨架

- 重构 `web/page.py` 的视觉骨架：
  - 左侧 permanent drawer。
  - 顶部 app bar。
  - 主题切换按钮。
  - 页面标题/副标题区域。
  - MUI 风格 button、chip、table、surface。
  - 移动端 drawer 折叠为横向 nav。
- 保留现有所有 API 调用和功能 tab。
- 验收：
  - `dashboard_html(api_base)` 保留 `{{API_BASE}}` 替换能力。
  - 不出现外部 URL。
  - 嵌入 Dashboard 和独立 Web 路由不变。

### P44-03 Web 骨架验证脚本

- 新增或扩展验证脚本，检查：
  - `ThemeMode` / theme toggle 标记。
  - sidebar/drawer/topbar 结构。
  - Workflows、Memory、Bridge、Maintenance 等核心 tab 保留。
  - `web/page.py` 小于 500 行。
  - 页面没有外部 CDN URL。
- 验收：`python scripts\check_web_shell.py` 通过，并纳入现有集成检查。

### P44-04 风险复盘页面骨架

- 在 Workflows tab 内预留风险复盘 detail 区：
  - policy summary。
  - executor trace。
  - proposal/advisor trace。
  - write steps 和 posture。
  - confirm/cancel action 区。
- 第一阶段可使用现有 detail JSON 数据，不强制新增 API。
- 验收：pending workflow 表和 detail 都能看到治理字段。

### P44-05 后续 React/Vite 迁移预案

- 如果无构建骨架稳定，再评估 `web/frontend/`：
  - React 18。
  - MUI 或 MUI-compatible token。
  - Vite build。
  - 构建产物嵌入 AstrBot 插件。
- 迁移前必须明确：
  - npm 依赖是否允许进入插件分发。
  - AstrBot 静态文件服务路径。
  - build 失败时是否保留无构建 fallback。

## 验证命令

```powershell
python -m compileall -q . C:\git\astrbot_plugin_plana_workflow_center
python scripts\check_workflow_integration.py
python scripts\check_astrbot_embed.py
python scripts\check_workflow_smoke.py
python scripts\check_workflow_split.py
python scripts\check_web_shell.py
python -c "import json; json.load(open('_conf_schema.json', encoding='utf-8')); json.load(open(r'C:\git\astrbot_plugin_plana_workflow_center\_conf_schema.json', encoding='utf-8')); print('json=ok')"
git diff --check
```

## 完成标准

- AstrBot 嵌入 Web 和独立 Web 均可继续使用。
- 页面结构进入 MUI 管理后台风格，具备 sidebar、topbar、theme toggle 和功能区骨架。
- 保留所有现有功能入口，不发生 API 路径回退。
- 后续复杂功能可以按页面模块逐步填充，而不是继续堆叠临时调试 UI。
