# Managed Service Integration Status

## Responsibility split

Core owns capability names, authorization, resource bindings, aliases, confirmation policy, and delivery policy. Adapter Gateway on 202 owns deterministic private-LAN API adapters. Codex receives only service references and capability declarations; it may generate candidates but does not receive service credentials, arbitrary endpoints, or final execution authority.

## Active read-only capabilities

| Service | Capability | Execution target | Confirmation |
| --- | --- | --- | --- |
| `ncqq.production` | Manager health, instances, bots, heartbeats, QR, stats, redacted logs, backend aliases, assets, restricted files and redacted config previews | 202 Gateway → 201 NCQQ | no confirmation for reads |
| `ani_rss.production` | status/about, subscription list/detail/search/preview, Mikan/AniBT/AnimeGarden catalog and subtitle groups, plus ANI-owned downloader reads | 202 Gateway → 200 ANI-RSS and port `7890` | no confirmation for reads |
| `qbittorrent.production` | torrent, transfer, file, category, property, tracker reads | 202 Gateway → 200 port `8080` | no confirmation for reads |
| `qbittorrent.tianxue` | torrent, transfer, file, category, property and tracker reads | 202 Gateway → 200 port `11080` | no confirmation for reads; mutations denied |
| `komga.production` | library, series, book, collection and read-list reads | 202 Gateway → 200 Komga | no confirmation for reads |

Production verification on 2026-07-18 additionally passed:

- `ani_rss.get_subscription`, `ani_rss.search_title`, and `ani_rss.list_recent_updates`.
- `ani_rss.list_download_tasks`, `ani_rss.download_transfer_status`, and `ani_rss.list_download_categories` against the ANI-owned qBittorrent on port `7890`.
- `ncqq.get_login_status` after resolving an instance from `ncqq.list_instances`.
- `qbittorrent.get_torrent` and `qbittorrent.list_files` after resolving a torrent hash from the list response.
- `tianxue_qb.list_torrents`, `tianxue_qb.transfer_status`, and `tianxue_qb.list_categories` against the Tianxue instance on port `11080`.
- Confirmed execute requests targeting `qbittorrent.ani` and `qbittorrent.tianxue` both fail closed with `service_write_capability_not_allowed`.
- Unknown `service_ref` and capability pairs fail closed with `service_capability_not_allowed`.

`ncqq.fetch_qrcode` was intentionally not triggered during acceptance because it creates a short-lived login artifact. The capability remains governed as artifact-only read access.
The production NAS also has two additional qBittorrent instances. They are not registered under `qbittorrent.production` because their data sets and lifecycle roles differ:

| Candidate service | Endpoint | Observed role | Registration state |
| --- | --- | --- | --- |
| `qbittorrent.ani` | 200 port `7890` | ANI-RSS downloader | `read_only_external`; exposed through `ani_rss.*` download capabilities and nested under `ani_rss.production` |
| `qbittorrent.tianxue` | 200 port `11080` | Tianxue dedicated seeding | `read_only_external`; exposed through `tianxue_qb.*` capabilities |

Only `qbittorrent.production` has mutation handlers. The ANI and Tianxue instances may be queried, but neither service reference is accepted by the Gateway execute route.

These adapters accept only registered scalar arguments and fixed API paths. They do not accept task-supplied URLs, methods, headers, credentials, shell commands, filesystem paths, or arbitrary request bodies.

## Confirmed workflow operations

- NCQQ start, stop, restart, pause, unpause, and kill use confirmed `ncqq.control_instance`. Instance creation, login refresh, registered-backend injection, and delete-with-data-retained are separate always-confirmed capabilities. Arbitrary OneBot calls, message sending, raw config writes, credential/account/connection CRUD, delete-with-data, and arbitrary paths remain denied.
- ANI-RSS add, enable/disable, refresh, refresh-all, and delete use confirmed Workflow capabilities. Delete always hard-codes `deleteFiles=false`.
- qBittorrent add, pause/resume/recheck/reannounce, category changes, and task removal target only `qbittorrent.production`. Task removal always hard-codes `deleteFiles=false`.
- Komga scan, analyze, library metadata refresh, and series metadata refresh require Core confirmation.
- Komga is available on 200 port `15600`. On 2026-07-18 a dedicated API key was stored under `komga.production.readonly` in the encrypted Gateway credential store. `komga.list_libraries`, `komga.search_series`, and `komga.list_recent` all passed production verification through `X-API-Key`; the key is not stored in Core configuration or exposed to Codex.

## Verified production state (2026-07-12)

- NCQQ Manager at 201 returned three instances, with one offline in the current snapshot.
- ANI-RSS at 200 returned four enabled subscriptions through the protected Bridge credential store.
- qBittorrent 5.0.2 at 200 returned four torrents and transfer status through projected read-only responses.
- qBittorrent ports `8080`, `7890`, and `11080` trust the complete `192.168.1.0/24` subnet; version and torrent APIs returned data without login from the LAN.
- ANI-RSS uses the dedicated qBittorrent instance on port `7890`; its configuration contains service credentials and must remain behind the credential boundary.
- ANI-RSS configuration files have inconsistent permissions, including legacy mode `0777` files.
- File Browser mounts the Unraid host root read-write while running as root. Core and Codex must never use it as a generic filesystem backend.
- Codex service descriptors contain no endpoint credentials.
- Core and Bridge restarted successfully after the capability deployment.

## Placement decision

- 200 remains the authority for resource state and storage-local operations.
- 201 Core remains the authority for bindings, permissions, confirmation, delivery, and audit.
- 201 Bridge executes deterministic allowlisted API calls and owns credential lookup.
- 202 Codex runs reviewed workflows using opaque service references and receives no NAS credentials, arbitrary endpoints, or final business execution grants.
- A future NAS connector should group services by trust boundary, with independent service references and capability allowlists.

## Adapter Gateway scope

Adapter Gateway is a generic deterministic integration boundary, not a NAS-only service. NAS applications are the first deployed trust boundary, but the same contract may support cloud APIs, repository services, monitoring systems, home automation, document platforms, or business systems when each integration provides:

- a fixed `service_ref` and explicit capability allowlist;
- scalar argument schemas with no caller-supplied URL, method, header, credential, shell command, or filesystem path;
- a dedicated credential reference owned by the Gateway or resource-local connector;
- read-only projection by default and Core confirmation for every mutation;
- health, audit, timeout, retry, and redacted result behavior.

Do not turn Adapter Gateway into a generic HTTP proxy. Add adapters by trust boundary and keep data-local connectors near the system that owns the data.

The Capability Center performs a cached, read-only representative probe for each registered service boundary. A successful representative probe marks capabilities on the same fixed adapter as operationally available while preserving the exact probe capability in evidence. Missing credentials are shown as restricted configuration rather than as an unverified or disconnected capability. Artifact-producing operations such as QR retrieval are never triggered automatically by health checks.
