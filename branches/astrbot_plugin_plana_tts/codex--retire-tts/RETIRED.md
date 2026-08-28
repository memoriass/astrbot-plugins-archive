# Retirement Notice

Plana TTS was retired on 2026-07-21.

## Runtime Status

- The AstrBot entrypoint is an inert compatibility shell.
- No commands, Web APIs, Core services, loopback HTTP servers, TTS providers, external API clients, cleanup jobs, or background workers are registered or started.
- The retired entrypoint does not create, inspect, clean, migrate, or delete audio directories and files.
- Historical implementation modules and configuration schemas remain for audit and data interpretation only.

## Replacement

There is no supported runtime replacement in this repository. Plana Core voice output should remain disabled until a separately reviewed voice implementation is selected and integrated.

New deployments must not depend on `/plana_tts`, `/plana_tts_status`, `/plana_tts/state`, `/plana_tts/synthesize`, `core_service`, or the historical loopback server.

## Repository Policy

Retirement does not rename the repository, delete stored audio, remove backend code, or rewrite existing configuration. Historical modules must not be imported by the AstrBot entrypoint.
