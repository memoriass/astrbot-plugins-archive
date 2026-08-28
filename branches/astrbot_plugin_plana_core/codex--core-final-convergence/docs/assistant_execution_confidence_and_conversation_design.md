# Assistant Execution Confidence And Conversation Design

## Purpose

This document is the long-lived design record for evolving Plana Core from a
workflow-oriented control surface into a practical, memory-aware assistant. It
captures the evidence, boundaries, and implementation direction agreed during
real ChatUI testing so later reviews can recover the rationale without relying
on conversation history.

## Evidence Base

The behavioral reference is the exported QQ history for group `885617919`
(`小饼干回收部`) under `C:\git\plana_qq_history_bootstrap\input`. The primary
Xiaowei account in that sample is `3950564652`.

Observed reusable behavior:

- Replies target the user's goal rather than narrating intent classification or
  internal tool routing.
- Reply anchors, name invocation, recent capability use, and a short observation
  window support natural follow-ups such as “现在呢”, “再来一次”, and “改回来”.
- Persona wording wraps facts, status, recovery, and artifacts; it does not
  replace them.
- Tool work is delivered as acknowledgement only when needed, followed by the
  result or artifact. Low-risk queries usually return only the final answer.
- Failures commonly lead to correction or redelivery instead of asking the user
  to restate the task.
- Familiarity and affinity influence tone, initiative, and confidence in
  resolving shorthand, but do not grant authorization.

Production ChatUI testing exposed the opposite behavior in Core:

- `WorkflowResult` fields such as `status`, `advisor`, `risk`, step IDs,
  capability names, and raw JSON were sent directly to users.
- Internal routing terms such as Workflow Center, Hermes lane, relay task ID,
  and capability errors displaced the actual answer.
- A successful workflow execution could still fail the user goal because no
  result interpretation layer converted tool output into a useful answer.
- Generic recovery text shifted work back to the user even when Core could retry,
  re-resolve a capability, preserve an artifact, or use a compensation action.

## Product Principle

Core must optimize for user-goal completion, not workflow completion.

The internal lifecycle remains structured and auditable:

```
conversation -> controlled decision -> capability execution -> structured result
```

The user-facing lifecycle adds interpretation and delivery:

```
structured result -> user outcome -> conversational presentation -> continuation state
```

Internal protocol fields remain available through audit records, the dashboard,
route trace, and a future `/plana why` surface. They are hidden from normal chat.

## Execution Postures

Risk is not equivalent to “read versus write”. Core evaluates scope,
reversibility, API constraints, resource protection, permissions, ambiguity,
and recovery support.

### observe

Automatic execution for search, listing, diagnostics, status, network probes,
workspace reads, previews, and artifact retrieval.

### reversible

Automatic execution for a single, bounded change when Core can record the
previous state and generate a compensation action. Examples include toggling a
notification, pausing a download, changing a tag, or updating a test resource.

### bounded_mutation

Automatic execution for a small mutation through a registered API whose schema,
resource scope, and server-side permissions prevent arbitrary host operations.
The operation must use a formally bound resource, avoid protected targets, and
verify the post-state.

### confirm_required

Confirmation is required for ambiguous targets, multi-resource changes,
production interruption, account-state changes, destructive file behavior,
irreversible actions, or operations without a reliable compensation path.
Confirmation text must describe the exact target, impact, and expected recovery.

### blocked

Core rejects credential access, protected system paths, unrestricted destructive
shell behavior, attempts to override formal resource identity, unregistered
capabilities, and operations prohibited by target or command policy.

## Protection And Exclusion Policy

A single blacklist is insufficient. Core uses several controlled lists:

- Protected resources: production bots, infrastructure services, credential
  stores, backup roots, and critical storage locations.
- Automatic-operation resources: test instances, temporary workspaces, and
  explicitly approved low-impact targets.
- Blocked behaviors: semantic and structured restrictions on destructive shell,
  credential extraction, boundary bypass, and unbounded deletion.
- Capability target exclusions: protected torrent tags, storage paths, bot
  instances, subscriptions, projects, or accounts that a capability cannot
  modify automatically.

These policies supplement capability schemas, resource bindings, server-side
API authorization, impact limits, audit records, and compensation actions.

## Change Journal

Reversible and bounded mutations create a durable `ChangeRecord` containing:

- resource and capability references;
- actor, scope, request message, and delivery identity;
- normalized input;
- before and after state;
- compensation capability and input;
- execution and verification status;
- expiry of the automatic undo window;
- audit source and policy decision.

Natural-language cancellation resolves through reply anchor, actor, recent
resource, and latest eligible change. Users should be able to say “撤销”, “改回
来”, or “刚才那个不对” without entering a numeric run ID.

## Relationship And Confidence

Relationship state may include familiarity, affinity, interaction count,
successful task history, preferred address, communication style, and proactive
preference.

Relationship state can influence:

- nickname and tone;
- willingness to infer shorthand from recent context;
- whether to offer a useful next action;
- how proactively Core retries or repairs a low-risk task;
- participation level in group conversation.

Relationship state cannot grant permissions, bypass resource bindings, expose
another user's artifact, or lower a protected resource boundary.

Execution confidence is calculated from controlled evidence:

- explicit intent and capability evidence;
- entity resolution and formal resource binding;
- reply-chain and recent conversation state;
- historical success with the same capability and resource;
- registered API boundary and server-side permission;
- reversibility and compensation support;
- ambiguity, impact scope, target protection, and failure history.

The model may provide semantic candidates, but local policy owns the final
execution posture.

## Conversation Frame

Core should maintain short-lived actor-and-scope continuation state:

- active goal;
- service and resource references;
- last capability and result reference;
- artifact references;
- pending or running task reference;
- recent entities;
- reply anchor;
- last reversible change;
- expiry and confidence evidence.

This state handles follow-ups such as “现在呢”, “再刷新”, “把它发给我”, “换另
一个”, and “取消刚才那个”. Operational continuation is not durable personal
memory.

## Result Interpretation

Execution produces structured `WorkflowResult` and capability outputs. A user
outcome layer converts them into:

- completion state;
- primary answer;
- important facts;
- artifact and delivery state;
- optional next actions;
- one actionable recovery step on failure;
- a debug reference for audit, not normal chat.

Examples:

- Empty `task.list` becomes “目前没有待办任务，队列是空的。”
- A successful NCQQ QR fetch reports the bound instance, login state, private
  delivery result, and QR expiry without exposing runner paths.
- A failed service query reports how far execution progressed and the exact safe
  recovery action.
- Hermes delegation says the task is running in the background; lane and relay
  IDs remain hidden unless requested.

## Message Lifecycle

- Immediate low-risk query: final answer only.
- Short artifact task: at most one progress message and one final artifact.
- Long Hermes task: one delegated notice, state-change-only progress, and one
  terminal result.
- Confirmation: exact target, mutation, impact, and recovery.
- Failure: explicit cause, preserved result or artifact state, and one executable
  recovery suggestion.
- Internal routing changes: silent by default.

## Architecture Direction

The target layers are:

1. `ConversationFrameStore` for transient continuation.
2. `ExecutionConfidencePolicy` for posture selection.
3. `ChangeJournal` for reversible operations.
4. `WorkflowUserPresenter` and capability-specific presenters for user replies.
5. `WorkflowDebugView` for dashboard, audit, and `/plana why`.
6. `RelationshipState` as advisory tone and interpretation evidence.

Core remains generic. NCQQ, ANI, qBittorrent, Komanga, NAS downloaders, cloud
management, and game automation expose registered service capabilities and
resource boundaries rather than dedicated chat plugins.

## Delivery Phases

### P0

- Separate debug formatting from normal user presentation.
- Hide workflow protocol fields in chat.
- Add semantic presentation for task lists, common statuses, artifacts,
  confirmations, and failures.
- Keep raw debug output available through explicit diagnostic surfaces.

### P1

- Add ConversationFrame and result references.
- Add ChangeJournal and natural-language undo.
- Add bounded mutation policy and protected target rules.
- Add one automatic recovery attempt before asking the user.

### P2

- Add RelationshipState and affinity-based tone.
- Add controlled group participation and proactive follow-up.
- Evaluate multimodal and companion behavior without weakening authorization.

## Acceptance

- Normal chat never exposes advisor, risk, step IDs, internal capability names,
  runner IDs, or raw JSON unless explicitly requested.
- Empty and successful read results answer the user goal directly.
- Low-risk bounded API actions run without unnecessary confirmation.
- Reversible changes can be undone through natural language.
- Protected resources and dangerous behavior never become automatic because of
  affinity or prior success.
- Failures preserve artifacts and provide one concrete recovery action.
- All user-facing statements remain derivable from structured execution facts.
