# Plana Core Progress — 2026-07-15

## Completed In This Rollout

- WebChat now keeps a session-bound WebSocket after the current response finishes, so Hermes callbacks appear without refreshing the page.
- Proactive text and media create independent bot records. Media placeholders are mounted immediately and resolved asynchronously, avoiding blank callback cards.
- Remote task terminal transitions are atomic. A cancelled task cannot be revived by a late success; `cancelling + succeeded` is recorded as `cancel_failed` instead of being delivered as success.
- Cancellation resolves the replied task, an explicit title, the current user's unique active task, or a short numbered disambiguation list. Natural phrases such as `不要了` are supported.
- Result delivery uses the immutable original conversation context. Private-only artifacts never fall back to a group when a private destination is unavailable.
- Artifact resend intent is classified as a low-risk short artifact action and reuses the existing authorized artifact reference.
- Hermes execution learning stores bounded execution evidence separately from user memory. Only verified low-risk lessons can become active; generated skills remain review candidates and permission-expanding records are quarantined.

## Production Evidence

- 201 AstrBot and WebUI remained healthy after the Dashboard deployment; WebUI returned HTTP 200.
- A short Hermes task returned `WebChat异步文字实时回流通过-0715` live in ChatUI without refresh.
- A structured Hermes result mounted its PNG card in the existing ChatUI session instead of leaving a blank message.
- A contextual `stop` cancelled Runner task `plana-1784080212-c65e7cb1baf7` on both 201 and 202. No late result appeared after an additional 18-second observation window.
- The first post-deployment Hermes probe exposed an empty `delivery_context`: Runner and Core both reached `succeeded`, but ChatUI could only recover the result after reload. Core now derives an immutable delivery context from the authorization event before delegation.
- After the fix, the production probe `投递上下文修复通过-0715-0210` returned live in the same ChatUI session without refresh; its stored source message, conversation, actor and artifact recipient all match the originating turn.
- 202 health continued to report `executes_tasks=true`, one interactive worker, one long worker, and no queued or running task after the tests.

## Automated Evidence

- Core targeted checks pass for cancellation, delivery isolation, native routing, behavior orchestration, delivery context, submission guards, renderer policy, remote learning, Web shell and Workflow integration.
- All remaining local checks pass when AstrBot-dependent checks use `C:\git\AstrBot\.venv\Scripts\python.exe` and the Xiaowei replay receives its fixture explicitly.
- AstrBot Dashboard `vue-tsc --noEmit` passes. The production-compatible Dashboard build also passed against exact production commit `ae44b912` before deployment.
- `python -m compileall -q .` and `git diff --check` pass.

## Xiaowei Replay Review

- The 50-scenario automatically labelled fixture currently reports `action=0.78`, `media=1.00`, and `delivery=0.88`; deterministic artifact-resend classification reduced raw mismatches from 22 to 17.
- The media policy is stable. The action and delivery scores are not yet release gates because the fixture does not preserve a reliable trigger message index and contains category false positives.
- This rollout fixes only deterministic, low-risk gaps such as artifact resend. It deliberately does not broaden proactive group participation or classify every sentence containing `不是` as a correction.
- The next evaluation step is manual trigger-index relabelling followed by real QQ two-user concurrency and reply-anchor replay.

## Remaining Work

- Deploy and gray-test the new remote-learning and Dashboard governance views on 201; production currently contains the cancellation/delivery files and WebChat callback patch, but not the full learning UI set.
- Complete real QQ tests for two-user concurrent artifacts, private-only delivery failure, reply-anchored cancellation, artifact resend and late callback isolation.
- Add an explicit administrator review transition for Hermes-generated Skill candidates; Runner output must never directly activate a generated capability.
- Restore dense embedding/reranker connectivity or document Sparse/FTS/RRF as the accepted production retrieval mode.
- Manually relabel the 50 Xiaowei scenarios before enforcing participation-rate targets.
- Keep large build, browser automation and multi-artifact stress tests serialized on 202 and continue monitoring memory, Swap and Runner recovery.

## Git Scope

- Core branch: `codex/core-full-rollout-20260714`.
- AstrBot Dashboard is committed separately because the AstrBot repository contains unrelated local modifications.
- Bridge Gateway remains a separate branch and repository; only intentional Bridge changes should be staged there.
