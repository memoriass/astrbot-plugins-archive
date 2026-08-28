# Plana TTS Architecture

Status: independent experimental track; excluded from the current Plana release readiness matrix.

## Role

Plana TTS is a companion AstrBot plugin for optional voice synthesis. It provides
voice capability to Plana Core while keeping provider selection and backend
configuration outside Core.

The whole service defaults to off. Fresh installs do not process commands or
register Core-facing HTTP APIs until the operator explicitly enables them.

## Runtime Flow

1. `main.py` imports the AstrBot plugin class from `voice/runtime.py`.
2. `voice/runtime.py` normalizes plugin config and exposes a controlled
   `core_service` when `enable_core_api=true`.
3. In the same AstrBot process, Plana Core discovers that service through the
   plugin registry. Split-process deployments may explicitly enable the
   `127.0.0.1:6191` HTTP fallback and authenticate with `X-Plana-Core-Key`.
4. Core submits contract `plana.voice.synthesis.v1`, text, session origin, and
   message type. The plugin validates its own switch and Core API boundary,
   session type, text length, and selected engine.
5. `astrbot_provider` calls AstrBot's configured TTS Provider for the current
   `unified_msg_origin`; `external_api` calls the configured external HTTP TTS
   service only when `external_api_enabled=true`.
6. The generated local audio path is returned to Core with `request_id`,
   `duration_ms`, `audio_bytes`, `format_verified`, `verification_level`, and stable error metadata. Direct `/plana_tts`
   command use returns the same audio as an AstrBot `Record` component.
7. Managed audio files are cleaned with a TTL policy during plugin startup.

## Module Boundaries

- `main.py`: AstrBot loader entry only. Keep it limited to importing and
  re-exporting the plugin class.
- `voice/runtime.py`: runtime configuration, command handlers, lifecycle,
  validation, and engine dispatch.
- `voice/core_service.py`: controlled synthesis/status surface shared by both
  transports.
- `voice/core_server.py`: optional loopback-only HTTP fallback with a dedicated
  Core service key; it is not a Dashboard or cross-host API.
- `voice/external_api.py`: external HTTP TTS backend. It posts JSON to the
  configured endpoint, accepts binary audio or JSON audio references, and writes
  managed audio files under the plugin data directory. It rejects empty audio and
  obvious format mismatches before returning success.
  Responses and downloads are capped at 20 MiB; JSON audio paths must stay under the managed audio root, and returned audio URLs must use HTTP(S) on the configured backend host.
- `_conf_schema.json`: operator-facing config schema.
- `scripts/check_tts_plugin.py`: read-only contract and structure check.

Future engines should be split into focused `voice/` modules before the runtime file
approaches the project line-limit rule. The repository root should stay limited
to AstrBot entrypoint files, metadata, docs, static assets, and verification
scripts.

## Backends

- `astrbot_provider`: uses AstrBot's configured TTS Provider.
- `external_api`: implemented but default-off. Operators must enable the plugin
  service, configure `external_api_url`, and explicitly set
  `external_api_enabled=true`.
- `sovits`: future SoVITS-compatible backend with its own base URL and synthesis
  parameters.

Neither backend should call Plana Core directly or write Core storage.
Core should not receive external API tokens, SoVITS parameters, or provider
selection details beyond the returned engine/status metadata. SoVITS stays a
plugin-side engine boundary and never becomes a Core executor capability.
