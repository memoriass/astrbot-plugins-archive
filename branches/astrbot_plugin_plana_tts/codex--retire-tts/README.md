# Plana TTS（已退役）

> **本仓库已于 2026-07-21 退役。请勿在新部署中启用。**

本仓库仅保留历史 Voice Runtime、后端适配、安全检查和音频存储实现供审计，不再提供 AstrBot 运行时能力。

当前 AstrBot 入口是无副作用兼容壳：

- 不创建或清理音频目录；
- 不注册 `/plana_tts` 或 `/plana_tts_status` 命令；
- 不暴露 `core_service`、Dashboard API 或 loopback HTTP；
- 不调用 AstrBot TTS Provider 或外部 TTS API；
- 不启动清理任务、网络服务或并发 worker；
- 不删除、迁移或改写已有音频文件与配置。

Plana Core 的语音输出应保持关闭，直到选择并接入新的受支持语音实现。历史配置和 API 不再受支持，详见 `RETIRED.md`。

## 归档结构

- `main.py`: 已退役的 inert AstrBot 兼容入口。
- `voice/`: 退役前 Voice Runtime、后端和存储实现。
- `docs/voice_runtime_adr.md`: 历史架构决策记录。
- `scripts/check_tts_plugin.py`: 归档结构、退役入口与历史组件检查。

## 验证

```powershell
python -m compileall -q .
python scripts\check_tts_plugin.py
git diff --check
```
