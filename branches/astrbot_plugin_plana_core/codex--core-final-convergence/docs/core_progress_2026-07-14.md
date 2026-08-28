# Plana Core Progress — 2026-07-14

## Production Topology

- `192.168.1.201`: AstrBot v4.25.5, Plana Core, Bridge Gateway and loopback renderer.
- `192.168.1.202`: Hermes Runner and Adapter Gateway under `/home/ubuntu/hermes`.
- Hermes health reports `executes_tasks=true`; its default model is `deepseek-v4-pro` after the previous models repeatedly exceeded the practical timeout.
- Renderer listens only on `127.0.0.1:6190`; Core remains the sole message-delivery owner.

## Completed Implementation

### Core Structure

- Split the previous oversized dialogue, memory, bridge, runtime and Hermes runner modules into responsibility-based files below the project 500-line boundary.
- Restored AstrBot event registration by keeping decorated wrappers directly on `PlanaCorePlugin` and delegating implementation to `plugin/plugin_events.py`.
- Added bounded service-query normalization for NCQQ, ANI-RSS, qBittorrent and Komga without embedding service credentials or arbitrary URLs in Core.
- Generic model-invented Hermes labels such as `text_response` now normalize to the registered `assistant.execution_handoff` only when no explicit service reference is supplied.

### Native Dialogue And Memory

- qB, NCQQ and ANI-RSS read-only requests run through AstrBot Tool Loop and do not enter Workflow Center or pending confirmation.
- Explicit memory recall now runs through a memory-only request ToolSet and lets the main model summarize real evidence. It cannot create a workflow or hand off to Hermes.
- Allowed tool history is kept only when every assistant tool call has a matching tool result. The previously failing old ChatUI conversation now completes without provider 400.
- Short Hermes text results return as text. Structured, long, non-text or multi-artifact results remain eligible for the external task-result card.

### Hermes 202

- Runner adapter uses the non-interactive Hermes CLI and returns real model output rather than the old stub.
- The production gray suite passed `30/30`, covering health, allowlist, invalid input, disabled lanes, real short/long tasks, artifact hash/download, multiple artifacts, cancellation, concurrency, restart and stuck-task checks.
- Final result file: `/home/ubuntu/hermes/data/runner/gray-20260714-final.json`.
- Direct test artifacts were created under `/home/ubuntu/hermes/data/hermes-home/gray-test/`.

### Renderer 201

- Deployed the complete renderer tree instead of a partial overlay, restoring the missing `resource_status` template and bundled Chinese fonts.
- Production unit tests pass `9/9`.
- Transparent `resource_status` output now renders Chinese correctly, hides duplicate internal metadata and crops to content height. Verified PNG: `920x587`, alpha channel present, bottom transparent gap `6px`.

## Real ChatUI Evidence

- qB: returned `firewalled`, `0 B/s` download/upload and four torrent records.
- NCQQ: reported `codex-qr-test-07120029` offline while `arona` and `plana` remained online.
- ANI-RSS: returned four enabled subscriptions with current episode progress.
- Hermes short task: returned exactly `短任务文字回流正常` as text after callback persistence and page refresh.
- Structured Hermes result: produced a task-result image without duplicate final text.
- Memory recall: called one recall tool and returned a natural evidence-based answer without Workflow Center.
- AstrBot KB: answered from the `基础插件指南` knowledge base and identified `@llm_tool`, `InternalAgentSubStage` and `ToolLoopAgentRunner`.
- Old conversation regression: the conversation that previously failed on orphaned `tool_calls` returned `旧会话历史清理正常` with no new 400 log.

## Replay And Automated Evidence

- Xiaowei replay fixture: 50 scenarios, current raw rates `action=0.68`, `media=1.00`, `delivery=0.88`.
- The 22 raw mismatches are not all Core defects: automatic labels contain false positives such as “停机后” as cancellation, input images as image recommendation and ordinary explanation questions as correction.
- Deterministic behavior and gallery checks still pass; the fixture needs manual trigger-index and expected-action review before it can be used as a release gate.

## Remaining Work

- Komga production read remains blocked until a dedicated read-only credential reference is supplied; Core must not derive one from an administrator account.
- WebChat asynchronous results are persisted and delivered, but the current client may require refresh before showing callback messages live.
- Contextual group cancellation, two-user concurrent artifact delivery and late-success-versus-cancel conflict still require real QQ group testing, although the direct Hermes gray suite covers queue cancellation.
- The 50 Xiaowei scenarios require manual relabeling and real group replay before enforcing the target participation and interruption rates.
- External embedding/reranker connectivity remains degraded; Sparse/FTS/RRF fallback works, but dense retrieval quality is not a completed production acceptance item.
- Renderer source is a separate dirty repository and was deployed but intentionally not included in this Core Git commit.

## Release Evidence

- Branch: `codex/core-full-rollout-20260714`.
- Baseline before this rollout: `defd6df chore: archive core integration baseline`.
- Core release validation must include compileall, all curated `scripts/check_*.py`, the 30-case Hermes result, production ChatUI evidence and `git diff --check`.
