# Card Rendering

图片卡片渲染层。

## 文件

- `rendering.py`: 渲染入口、卡片宽度/缩放选择和卡片类型分发。
- `generic_cards.py`: 通用卡和添加成功卡模板。
- `media.py`: logo、Mikan 图标、封面图抓取、封面缓存、ANI-RSS 图片代理 URL。
- `blocks.py`: 通用文本块、表格、徽标、URL 断行渲染。
- `mikan_cards.py`: Mikan 候选卡整卡识别和 HTML 组装。
- `mikan_rows.py`: Mikan 候选表格解析、候选行和候选卡片渲染。

## 渲染模式

由插件配置 `render_mode` 控制：

- `image`: 只发送图片卡片。
- `text`: 只发送文本。
- `both`: 图片卡片加简短文本 caption。

渲染失败时自动回退为文本，避免工作流中断。

## Linux 兼容

`pylitehtml 0.2.1` 在 PyPI 提供 `manylinux_2_34` wheel，Ubuntu 22.04/24.04
这类 glibc 版本较新的环境可通过 pip/uv 正常安装。更旧的 Linux 发行版如果无法
安装或加载渲染器，插件会自动按文本结果发送，不影响订阅流程。

## 卡片类型

- Mikan 搜索/推荐候选卡。
- Mikan 字幕组 RSS 列表卡。
- ANI-RSS 已启用订阅列表卡。
- RSS 直连确认卡。
- 添加订阅成功卡。
- 通用文本卡。

成功卡片使用紧凑宽度，交互候选卡按内容选择宽度。
