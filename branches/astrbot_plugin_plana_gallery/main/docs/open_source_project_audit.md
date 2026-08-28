# Gallery 开源架构参考结论

复审日期：2026-07-14

## 采用的原则

- 借鉴 Lychee 一类照片管理项目的本地资产浏览、相册式网格和 metadata 整理体验。
- 借鉴 Lsky 的清晰资产管理入口，但不保留外部发布、provider 或图床职责。
- 借鉴 Immich 的 canonical data 与可重建派生索引分离原则，不引入其完整服务、移动备份、人脸识别或机器学习栈。
- 借鉴数据集审核工具的人工 review、候选解释和反馈评测，不允许模型自动批准标签。

## 当前裁决

- 图片文件、SHA-256、`asset_ref`、标签和审核记录是事实源。
- SQLite FTS5 是可重建候选索引。
- Core 只通过版本化本机 API 获取候选，不直接打开 Gallery SQLite。
- 模型只能选择返回的 `asset_ref` 或 `none`。
- `needs-review`、`safety:restricted`、失效路径和已删除资产不得进入生产候选。
- 首期不引入 OpenCLIP、向量数据库、外部图库或自动训练。

## 后续评测

1. 维护真实聊天语境与人工相关性 fixture。
2. 比较 exact facet、alias、FTS 和反馈调权后的候选顺序。
3. 观察 delivered 与 negative 反馈是否降低重复和误配。
4. 只有在 20,000 张以上数据证明 tag/FTS 不足时，再评估可选离线 embedding。
