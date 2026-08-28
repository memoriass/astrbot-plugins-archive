# ADR: 独立 Voice Runtime 边界

## 状态

实验轨，暂不并入 Plana Core 发布清单。

## 决策

- 当前插件只负责有界文本到音频文件的合成、格式验证、配额、TTL 和错误元数据。
- 参考 Pipecat 的 frame/pipeline 分层与 LiveKit Agents 的 session/telemetry，但不在本插件实现实时会话。
- ASR、VAD、语音轮次、打断、流式播放、长连接和设备状态属于未来独立 Voice Runtime。
- Core 只消费稳定合成结果或未来 Voice Runtime 的受控事件，不保存模型参数、实时状态机或设备连接。

未来数据流为 `audio input -> VAD -> ASR frames -> controlled agent turn -> TTS frames -> interruptible output`。每个 frame 带 session、turn、sequence、时间戳和 trace id；打断是显式控制 frame，遥测不记录原始音频或密钥。

## 禁止项

- 不把实时状态机或长连接注册到 Core。
- 不自动下载模型，不访问生产 TTS backend，不将音频上传第三方。
- 不因候选模型输出直接改变授权、发送目标或会话状态。
