# TTS 开源项目代码审计

审计日期：2026-07-12

## 1. 当前仓库基线

- 分支 `main`，版本 `0.1.0-beta.1`，审计时有 8 个未提交项；直接在 `main` 开发是发布纪律风险。
- 默认关闭；Core API、external API backend 均需显式开启。
- contract 为 `plana.voice.synthesis.v1`，返回 request id、duration、audio bytes、format verification 和本地受控路径。
- 支持 AstrBot provider 和 external API；SoVITS 仅保留后端边界。启动时执行 managed audio TTL 清理。
- 2026-07-12 验证：compileall、`scripts/check_tts_plugin.py`、`git diff --check` 均通过；存在 LF/CRLF 提示。

## 2. 发现清单

### P0

1. **在 `main` 上保留未提交开发改动。** 应先切稳定 feature branch、冻结 beta 基线，再进行后端扩展。

### P1

1. **错误模型不够稳定。** external API 有具体错误字符串，但 contract 尚未定义统一 error code、retryable、backend status 和安全错误摘要。
2. **音频验证仍是轻量 magic-byte 检查。** 能阻止明显格式错配，但无法证明完整可解码、时长正确、无截断或扩展名与编码一致。
3. **并发和资源上限未证明。** 缺少同时请求、单请求最大音频、下载流上限、磁盘配额、慢响应和取消测试。
4. **TTL 清理只在启动执行。** 长期运行时会积累文件；需要受控周期清理、in-use lease 和删除失败记录。
5. **外部 audio URL 下载边界需要 SSRF 审查。** 应限制 scheme、host policy、redirect、private address、content length 和 timeout，不能把外部 URL 视为可信音频。

### P2

1. **实时语音不是 TTS 插件的自然扩展。** ASR、VAD、打断、流式播放、turn-taking 和长连接需要独立 Voice Runtime。
2. **不应自建完整 TTS 模型生态。** 优先复用 AstrBot provider 或受控 external backend。

## 3. 开源候选矩阵

| 项目 | 许可证/近期状态 | 可借鉴机制 | 依赖成本 | 裁决 |
| --- | --- | --- | --- | --- |
| `pipecat-ai/pipecat` | BSD-2-Clause；2026-07-11 推送；release `v1.5.0` | 流式 pipeline、VAD、打断、frames、服务适配 | 高于纯 TTS | 未来 Voice Runtime 首选参考 |
| `livekit/agents` | Apache-2.0；2026-07-11 推送；release `livekit-agents@1.6.5` | 实时 room、turn detection、agent session、telemetry | 高，需要 LiveKit 生态 | 适合跨设备实时语音，不进入 TTS |
| `rhasspy/piper` | MIT；仓库已 archived，最后推送 2025-08-26 | 本地轻量合成和模型分发 | 中，维护已停止 | 不新增依赖，仅作历史参考 |
| AstrBot TTS provider（本地） | 宿主能力 | provider selection、平台音频发送 | 已有依赖 | 当前首选后端 |

官方来源：

- `https://github.com/pipecat-ai/pipecat`
- `https://github.com/livekit/agents`
- `https://github.com/rhasspy/piper`

## 4. 深审结论

### 可直接借鉴

- Pipecat 的 frame/error/metrics 分离思想，用于定义请求、音频结果和 backend error metadata。
- LiveKit 的 session/turn telemetry 只用于未来 Voice Runtime 设计。
- AstrBot provider 继续作为默认集成点，避免 Core 和 TTS 维护 provider SDK。

### 需适配借鉴

- external backend 返回统一 `request_id`、engine、format、duration、bytes、verified、retryable 和 error code。
- 可解码验证优先使用项目现有可选库或受控探测工具；没有依赖时保持 magic-byte 并明确 `verification_level=header_only`。
- 实时 voice 通过独立 contract 连接 Core/Bridge，只提交 transcript、turn event 和受控 delivery，不传设备控制权。

### 禁止引入

- 把 Pipecat/LiveKit 主循环嵌入 Core 或现有 TTS runtime。
- 将 SoVITS 模型参数、外部 token、设备状态和长连接 session 写入 Core。
- 新增 archived Piper 作为默认依赖。
- 接受任意 audio URL、无限下载或未经验证的本地路径。

## 5. 目标架构与数据流

```text
Core text request
  -> TTS validation/policy
  -> AstrBot provider or controlled external backend
  -> bounded managed audio
  -> decode/header verification + metadata
  -> Core/AstrBot Record delivery

Future realtime audio
  -> separate Voice Runtime
  -> transcript/turn/event contract
  -> Core policy and Bridge delivery
```

## 6. 实施任务

1. **冻结开发基线**：从 `main` 切 feature branch，确认 8 个改动归属并建立 beta tag。
2. **统一错误 contract**：定义 error code、stage、retryable、backend status、安全摘要和 request id；保持 v1 成功字段兼容。
3. **强化 audio URL policy**：scheme/host/redirect/private IP/content length/timeout 限制，下载使用临时文件后原子移动。
4. **并发与配额**：限制并发、输入文本、响应字节、单文件大小和目录总量；明确 overload 错误。
5. **验证等级**：返回 `verification_level`；有 decoder 时检查可解码与时长，无 decoder 时明确 header-only。
6. **运行期清理**：增加低频后台 TTL 清理、in-use lease、磁盘水位和失败计数，不删除正在发送的音频。
7. **Voice Runtime ADR**：只有出现实时通话需求时再设计独立插件，候选优先 Pipecat；评估 LiveKit 作为 transport，而非默认依赖。

验证：现有 check，加并发、超大响应、慢请求、redirect/SSRF、损坏音频、TTL/in-use、磁盘配额和 backend 4xx/5xx。

## 7. 最终裁决

- **立即实施**：分支基线、统一错误、URL policy、配额、运行期清理、验证等级。
- **验证后实施**：可选 decoder 深度验证和独立 Voice Runtime ADR。
- **暂缓**：实时语音实现。
- **拒绝**：Core 内实时音频循环、Piper 新默认依赖、任意 URL/路径和后端参数泄漏。

## 8. 实施后复审（2026-07-12）

- external backend 与 runtime 错误现在包含 error code、stage、retryable 和 verification level。
- 主响应、audio URL 和 base64 音频限制为 20 MiB；audio URL 仅允许配置后端同 host 的 HTTP(S)，禁止凭据 URL。
- JSON 返回的 audio path 必须位于 managed audio root；成功响应明确当前仅做 `header_only` 验证。
- 仍待完成：后台周期清理、并发 semaphore、目录总配额、真实 redirect/DNS rebinding 测试和可选 decoder 深度验证。
# 2026-07-12 独立实验轨复审

- 已增加合成 semaphore、单文件/目录总配额、低频 TTL 清理和 in-use lease。
- 外部 API 与音频下载禁用自动 redirect；本地 fake server 覆盖 redirect 与跨 host SSRF 拒绝。
- `docs/voice_runtime_adr.md` 固定 Pipecat/LiveKit 借鉴边界；实时 frame、interrupt、VAD、ASR 和 telemetry 不进入 Core。
- 本轮未注册 Core、未调用生产 backend，也未修改 Plana 发布清单。
