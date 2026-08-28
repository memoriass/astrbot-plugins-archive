# MCP Execution Governance

## Topology

- `192.168.1.201` runs AstrBot, Plana Core, ChatUI, the renderer, and governance decisions.
- `192.168.1.202` runs Codex Runner, Adapter Gateway, and task-scoped MCP processes.
- Resource-local connectors for Unraid/NAS services should run near `192.168.1.200` when they require filesystem or container-local access.
- MCP servers are not exposed to ChatUI or directly selected by model-generated command strings.

## Runtime policy

Codex task tools start only for a task that declares an allowed `service_ref`. The Runner maps service references to fixed local adapters or task-scoped MCP toolsets. Unknown references fail closed with `service_ref_not_allowed`.

Current registrations:

| Service reference | Purpose | Risk | Execution policy |
| --- | --- | --- | --- |
| `github.official` | GitHub repository and issue lookup | read-only | task-scoped stdio; 21 selected tools |
| `docs.context7` | current library documentation | read-only external lookup | task-scoped stdio |
| `browser.playwright` | browser automation | elevated | reviewed long tasks only; 19 selected tools |

The Playwright profile excludes arbitrary JavaScript evaluation, unsafe code execution, uploads, and drag/drop from the selected tool list. It uses an isolated browser context and does not run a listening HTTP service.

## Delegation contract

Core remains service-neutral. An approved execution envelope contains `service_ref`, `capability`, `credential_ref`, and normalized arguments. When delegated, Core copies the envelope service into top-level `service_refs`. Runner accepts only references present in its local allowlist and translates those references to fixed adapters or MCP toolsets.

Natural-language text cannot override a service reference, executable path, credential reference, or MCP command. Codex receives opaque registered references and redacted probe evidence rather than service secrets.

## Placement rules

- Keep deterministic low-risk AstrBot tools in the AstrBot native Tool Loop.
- Place documentation, GitHub research, and browser-heavy agent tasks on 202.
- Place NAS downloaders, storage indexers, Komga, qBittorrent, and other data-local connectors near 200; expose narrow capabilities rather than host shells.
- Use Adapter Gateway for deterministic non-agent service integrations across any trust boundary, including non-NAS services. It remains a fixed adapter registry, never an arbitrary URL or generic HTTP relay.
- Keep service state in the external manager, bindings and authorization in Core, and semantic aliases in memory.
- Do not create a new MCP relay for every API. Prefer one service adapter or MCP process per trust boundary and reuse Core's execution envelope.

For the current Unraid host, use one NAS trust boundary with separate service references: `qbittorrent.production`, `qbittorrent.ani`, `qbittorrent.legacy`, `ani_rss.production`, and `komga.production`. Each capability remains independently authorized by Core.

## Operations

- GitHub wrapper: `/home/ubuntu/mcp/scripts/run-github-stdio.sh`
- Context7 wrapper: `/home/ubuntu/mcp/scripts/run-context7-stdio.sh`
- Playwright wrapper: `/home/ubuntu/mcp/scripts/run-playwright-stdio.sh`
- Codex home: `/home/codex`
- Runner data: `/home/codex/data/runner`
- Task workspaces: `/home/codex/workspaces`
- Runner environment: `/etc/plana-codex.env`
- Adapter Gateway code: `/home/codex/service-gateway`
- Adapter Gateway data and encrypted credentials: `/home/codex/data/service-gateway`
- Adapter Gateway unit: `plana-service-gateway.service`

No MCP port in the former `8101-8110` range should listen while idle. `mcp-playwright.service` and `mcp-github.service` must not exist. Credentials remain in mode `0600` files and must not be copied into task text, logs, artifacts, or ChatUI messages.

## Verification status (2026-07-18)

- Official GitHub MCP `0.31.0`: stdio handshake and Runner delegation succeeded.
- Context7 MCP `3.2.3`: `undici` upgraded to `6.27.0`; production audit reports zero vulnerabilities; direct `resolve-library-id` succeeded.
- Playwright MCP: direct navigation to `https://example.com` succeeded using the installed Chrome binary.
- Codex Runner and Adapter Gateway health checks pass on 202. Candidate output and task-scoped Skill contracts are exposed by Runner health and verified by Core before use.
- Codex Runner lifecycle observations expose attempt identity, monotonic event sequence, heartbeat lease, and cancellation handshake timestamps. Bridge forwards only changed non-terminal observations; Core remains the authoritative lifecycle and audit store.
- Adapter Gateway was migrated away from the removed Hermes path and successfully restarted from `/home/codex/service-gateway` on 2026-07-18.


