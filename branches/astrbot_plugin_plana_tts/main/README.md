# Plana TTS（独立实验轨）

> 本仓库不进入当前 Plana 发布套件，不并入 Core 或 Bridge。其代码、安全测试和 Voice Runtime ADR 继续独立演进。

Plana TTS 是 Plana 插件族的可选语音合成附属插件。它给 Plana Core 提供语音
合成能力，同时由本插件自行控制实际来源：AstrBot TTS Provider、外部服务器
TTS、自建 SoVITS 等都属于本插件边界，Core 只发起受控合成请求。

整个 TTS 服务默认关闭。安装后不会处理 `/plana_tts`，也不会注册 Core 调用
API；用户需要手动开启 `enabled`，并按需开启 `enable_core_api` 或具体后端。

当前版本实现 `astrbot_provider` 和 `external_api` 引擎。`astrbot_provider`
调用当前会话配置的 AstrBot TTS Provider；`external_api` 调用用户配置的外部
HTTP TTS 服务，但默认关闭，用户完成 URL/token/payload 配置后需要手动开启。
`sovits` 仍是后续扩展位，选中时会明确返回未接入，不会静默降级或落回 Core。

## 命令

```text
/plana_tts <文本>        生成语音
/plana_tts_status        查看插件状态
```

## Core 接入

启用 `enable_core_api` 后，本插件注册：

```text
GET  /plana_tts/state
POST /plana_tts/synthesize
```

Core 侧将 `ops_voice.voice_synthesis_url` 指向 synthesize 端点。Core 不配置
TTS 来源，也不再填写 TTS token/header；本插件的 Core API 只接受无代理转发头的
本机回环请求，并返回本机音频文件路径供 Core 发送语音消息。

## 配置

- `enabled`: 总开关，默认 `false`。
- `enable_core_api`: 是否开放给 Plana Core 的受控合成入口，默认 `false`。
- `engine`: 当前可用值为 `astrbot_provider` / `external_api`；`sovits` 预留。
- `max_text_chars`: 单次合成文本长度上限。
- `allow_group` / `allow_private`: 会话类型开关。
- `external_api_enabled`: 外部 API 总开关，默认 `false`。
- `external_api_url` / `external_api_token`: 外部 HTTP TTS 服务地址和 Bearer Token。
- `external_api_timeout_seconds`: 外部 API 调用超时。
- `external_api_text_key`: POST JSON 中承载文本的字段名，默认 `text`。
- `external_api_voice` / `external_api_format`: 可选音色和音频格式参数。
- `external_api_extra_payload`: 可选 JSON object，会合并进外部 API payload。
- `sovits_base_url`: 后续 SoVITS 后端接入预留。

启用外部 API 的最小配置：

```text
enabled = true
engine = external_api
external_api_enabled = true
external_api_url = http://127.0.0.1:8000/tts
external_api_token = <optional bearer token>
```

如果要让 Core 调用本插件，还需要：

```text
enable_core_api = true
```

外部 API 可以直接返回音频二进制，也可以返回 JSON：

```json
{"audio_path": "C:/path/to/audio.wav"}
{"audio_base64": "...", "mime_type": "audio/wav"}
{"audio_url": "http://127.0.0.1:8000/result/audio.wav"}
```

## 边界

- 不读取或写入 Plana Core 数据库。
- 不注册 Core bridge payload 或 workflow capability。
- 不让 Core 接触外部 TTS API token、SoVITS 参数或后端选择。
- 不记录完整合成文本到日志。
- 外部 API 和后续 SoVITS 都必须保持独立 token、超时、输出文件校验和失败路径。

## 验证

## Source Layout

The repository root is reserved for AstrBot entrypoint files, metadata, docs,
the logo, and verification scripts.

- `main.py`: thin AstrBot loader that imports `PlanaTTSPlugin`.
- `voice/runtime.py`: runtime config, command handlers, Core API, validation,
  auth, and engine dispatch.
- `voice/external_api.py`: external HTTP TTS backend, response parsing, and
  managed audio-file output.
- `scripts/check_tts_plugin.py`: structure and contract check.

```powershell
python -m compileall -q .
python scripts\check_tts_plugin.py
git diff --check
```
