# Xiaowei Chat Behavior Reference

## Source

The review uses the exported QQ history for group `885617919` (小饼干回收部)
under `plana_qq_history_bootstrap/input`. The main Xiaowei account in the sample
is `3950564652`.

## Observed behavior

- 23,008 messages were emitted by the main Xiaowei account.
- 4,206 messages explicitly anchored a reply to another message.
- 7,676 messages carried a resource; 6,456 carried an image.
- Messages formed 14,262 response bursts; 5,427 bursts contained more than one
  message, with a maximum observed burst size of nine.
- For directly addressed messages followed by a response within five minutes,
  the median response delay was three seconds and the observed 90th percentile
  was 29 seconds.

These measurements describe the exported sample only. They are behavioral
references, not production service-level targets.

## Reusable patterns

1. Name invocation is treated as a real wake signal even without an explicit
   platform mention.
2. A short observation window allows natural follow-ups after the bot replies.
3. Tool work is commonly split into acknowledgement, execution status, and
   artifact delivery rather than one oversized response.
4. Results are anchored to the requesting message or user, which reduces group
   ambiguity when several tasks run concurrently.
5. Persona phrasing wraps tool use but does not replace status, errors, or
   artifacts.
6. The assistant behaves as a capability fabric: individual tools remain
   replaceable while conversation continuity stays in the assistant layer.

Daily conversation should acknowledge the content itself instead of turning
every message into an execution report. Avoid repeated names, excessive
honorifics, “stand by / command me” phrasing and unnecessary closing questions.
Recommendation media may accompany the answer when a real image is available;
a generated card must not duplicate the same answer text.

## Core adoption

- Plana name mentions now dispatch and open the familiar follow-up window.
- Read-only service capability context is retained for 180 seconds per
  scope-and-actor pair. Pronoun-style follow-ups can reuse the previous service;
  qBittorrent status wording switches from torrent listing to transfer status.
- Capability selection uses evidence scoring instead of registration order.
- Operational queries are blocked from durable user-memory extraction unless
  the user also provides an explicit stable preference, identity fact, promise,
  or remember request.

## Boundaries

- Do not copy Xiaowei-specific command names, personas, image pipelines, or
  account identifiers into Core.
- Do not treat high message volume as a target. Plana should avoid unsolicited
  group participation and should preserve its configured wake and observation
  windows.
- Multi-stage updates are appropriate for delegated or artifact-producing work;
  low-risk status queries should still return only the final result.

## Deep analysis

### Participation, memory, and tool intent

Xiaowei uses layered wake evidence: reply anchor, platform mention, configured name invocation, an actor-scoped follow-up window, and passive observation. Core should use that order. Passive observation may enrich short-lived context, but must never start a tool or Hermes task by itself.

Memory must be separated into transient conversation continuation, durable social preferences, resource-alias candidates, and operational events. Tool queries and temporary service state are not durable user facts. Memory may suggest an alias, but Core bindings remain authoritative for identity and permission.

Tool intent should be scored from controlled evidence: explicit capability, resolved resource alias, reply-chain inheritance, actor-scoped recent capability, then constrained semantic advice. The final local tuple is `service_ref`, `capability`, `resource_id`, `risk_class`, `execution_target`, and `delivery_policy`; the model cannot invent its members.

### Execution lifecycle

- Immediate read-only query: final result only.
- Short artifact task: one progress message and one final artifact.
- Hermes task: one delegated notice, state-change-only progress, one terminal result.
- Failure: explicit reason and one executable recovery suggestion.

All phases require the same immutable correlation context. Repeated generated-plan or confirmation templates make low-risk work appear unreliable.

### Concurrency and delivery gap

The history contains apparent cross-delivery during concurrent image tasks: the nearest requester and the user named by the artifact sometimes differ. This proves that natural interaction quality does not guarantee delivery correctness under concurrency.

Plana currently has the same structural risk: `TurnContext` has no source platform message ID or reply target; `remote_task_runs` has no immutable message anchor or artifact recipients; `proactive_tasks` does not make delivery identity a first-class contract; and Bridge sends terminal text and artifacts with `context.send_message(scope_id, ...)`, so the stored actor is not enforced at the final send boundary.

The task is correlated well enough for persistence, but not for safe human delivery. In a busy group, completion is effectively broadcast to the group instead of being attached to the originating request.

### Required delivery contract

Core should create an immutable `plana.delivery.v1` object at AstrBot ingress containing `conversation_id`, `source_message_id`, `reply_to_message_id`, `scope_id`, `actor_id`, display name, delivery mode, authorized artifact recipients, fallback mode, and creation time.

Hermes and adapters receive it as opaque metadata and cannot override it. Callbacks must match stored `request_id + scope_id + actor_id`; stored delivery data wins over callback fields. AstrBot already carries an incoming platform message ID, so Core should capture it at ingress instead of reconstructing it from recent group activity.

Delivery fallback order: reply to the source message; mention the same actor in the same scope; use an explicitly authorized private recipient for sensitive artifacts; otherwise retain an undelivered terminal result. Never redirect to the latest active user or latest task. QR codes and account-recovery artifacts require explicit private delivery policy.

### Cancellation

Current cancellation is safer than delivery because it selects active runs by `scope_id + actor_id` and asks for a task ID when ambiguous. Extend it in this order: replied task, explicit task ID, actor's only active task, then disambiguation. Administrators should cancel another actor's task only through an explicit reference.

Cancellation and correction language is now forced through deterministic task-session handling even when the generic dialogue analyzer classifies the turn as chat. The model must not claim that a task stopped unless Core or Hermes returned a cancellation terminal state.

Persist `cancel_requested`, `cancelled`, and `cancel_failed` separately. A local acknowledgement is not proof that Hermes stopped. A late success racing with a confirmed cancellation must become an audited terminal conflict, not an ordinary success.

### Generic context model

- `ConversationContext`: natural-language continuity by actor and reply chain.
- `ExecutionContext`: capability, normalized resource, risk, executor and cancellation state.
- `DeliveryContext`: immutable source message, recipients and fallback policy.

This supports NCQQ, ANI, qB, NAS, cloud, monitoring and future Hermes-generated workflows without service-specific chat plugins. Conversation and memory help interpret intent; neither can grant authorization.

### Required concurrency tests

1. Two users submit A/B in one group and B completes first; each result reaches its requester.
2. Artifact A cannot be delivered to requester B.
3. Duplicate callbacks persist and notify once.
4. Core/Bridge restart preserves delivery context.
5. Callback scope or actor conflicts are rejected or ignored.
6. Missing source message falls back to the same actor, never another speaker.
7. A departed actor produces an undelivered result, not rerouting.
8. Reply cancellation targets the anchored task; ambiguous bare cancellation asks for a task ID.
9. Cancellation/completion races produce one coherent audited terminal state.
10. Private artifact failure exposes no sensitive group payload and preserves administrator recovery.

### Priorities

- **P0:** immutable delivery context; policy-driven reply/mention/private sends; callback identity validation; reply-aware cancellation and terminal races.
- **P1:** one correlation ID across Core, Bridge, Hermes, renderer and artifact; anchored progress; resource-alias candidates; restart and reordered-result integration tests.
- **P2:** persona/social memory tuning, participation precision evaluation and a safe `/plana why` explanation surface.
