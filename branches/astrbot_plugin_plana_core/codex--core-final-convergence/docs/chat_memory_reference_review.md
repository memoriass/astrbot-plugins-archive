# Chat Memory Reference Review

## Source

- Source: external chat-memory reference implementation
- Audited reference: `8a27e72`
- Date: 2026-06-25

## Conclusion

The chat-memory reference has more relevant memory ideas for Plana than Hermes. The valuable
parts are not its full A_Memorix runtime, but the user-centered memory lifecycle:
identity binding, profile evidence, profile refresh, episode evidence, and
memory maintenance actions.

Plana should keep its AstrBot-native SQLite service boundary and borrow the
architecture selectively. Do not copy reference implementation code directly.

## High-value patterns to adapt

| Reference area | Plana adaptation |
| --- | --- |
| `person_info.bind_manager` cross-platform grouping | Extend Plana identity/scope alias into explicit account binding groups with confirmation and audit. |
| `person_profile_injector` candidate collection and prompt budget | Keep profile injection bounded by current participants, exclude bot identity, cap text size, and mark profile text as internal reference. |
| A_Memorix profile snapshots and refresh queue | Add profile snapshot/version table and refresh queue so profile changes are evidence-backed, TTL-bound and observable in Web. |
| A_Memorix relation lifecycle fields | Add memory/relation lifecycle states: active, protected, frozen/inactive, restored. Preserve audit and confirmation. |
| Episode and paragraph evidence chain | Add lightweight episode records linked to episodic memories, relations, and semantic entries for traceable long-term summaries. |
| `memory_service` thin facade | Keep Core-facing memory API thin; route writes through storage/service layers, not Web or command handlers. |
| `maintain_memory` actions | Expose reinforce/protect/freeze/restore as confirmed workflow steps and Web actions, never as direct LLM side effects. |
| `episode_service` deterministic fallback | Group pending evidence by source/time/size and produce a rule-based fallback episode when LLM segmentation fails. |
| `person_profile_service` evidence buckets | Classify profile evidence into stable buckets before prompt injection; demote uncertain or temporary facts into an explicit uncertainty bucket. |
| `relation_scanner` threshold/cooldown scanning | Use low-frequency candidate generation with participant filters and cooldowns, but route resulting writes through Plana feedback/workflow confirmation. |
| `memory_activator` candidate-id selection | Reinforce Plana's existing rule that LLMs select from local candidate IDs instead of inventing memory identifiers or write targets. |

## Additional code findings

### Episode evidence chain

Files reviewed:

- Episode service
- Episode segmentation service
- Episode retrieval service

Useful details:

- Pending paragraph rows are expanded through storage first, then grouped by
  `source`, time window, paragraph count and character budget. This is a good
  shape for Plana because it bounds LLM calls and keeps evidence provenance.
- LLM segmentation is required to return strict JSON and paragraph hashes must
  come from the input set. Invalid or empty output is rejected.
- If LLM segmentation fails, the reference still emits a deterministic fallback
  episode using snippets, participants, derived keywords and time metadata.
- Episode retrieval fuses lexical episode rows with projected paragraph and
  relation evidence. Plana can adapt this later as an explainable recall layer
  above existing `memory/recall.py` and `memory/query_planner.py`.

Plana landing:

- Add a small `memory/episodes.py` service and tables for `episode_records` and
  `episode_evidence_links`.
- Do not make episodes the source of truth for memory. Treat them as evidence
  bundles used for recall explanation, profile refresh and Web diagnostics.
- Keep every episode link tied to existing memory, semantic or relation IDs so
  deletion/freeze/protect policies can follow the original object.

### Profile evidence buckets

Files reviewed:

- Person profile service
- Person profile injector

Useful details:

- Profile refresh uses aliases plus relation/vector evidence, then stores a
  snapshot with TTL and evidence IDs.
- Evidence is bucketed into `identity_settings`,
  `relationship_settings`, `stable_facts`, `interaction_preferences`,
  `recent_interactions`, and `uncertain_notes`.
- There is a rule-based classifier fallback before optional LLM
  classification. This is important because profile generation should degrade
  to deterministic behavior rather than disappear.
- Prompt injection collects only current participants, excludes the bot's own
  identity, caps profile count and text length, and labels the block as internal
  reference.

Plana landing:

- Extend the current semantic/profile view with a profile snapshot table instead
  of replacing `semantic_memories`.
- Build a `memory/profile_evidence.py` classifier with rule-first buckets and
  optional LLM classification.
- In prompt context, inject only bounded profile summaries selected by current
  participants and scope aliases. Treat them as advisory and lower priority than
  the live conversation.

### Relation scan and memory activation

Files reviewed:

- Relation scanner
- Memory activator

Useful details:

- Relation scanning waits for a message threshold, filters bot self, requires
  known person IDs, and applies per-user cooldowns.
- The extraction prompt explicitly says not to infer facts; only clear
  statements should become impressions.
- The current reference implementation writes person memory points directly
  after LLM classification. That is too permissive for Plana.
- Memory activation assigns temporary candidate IDs and asks the LLM to choose
  from those IDs. Invalid IDs are discarded.

Plana landing:

- Keep the threshold/cooldown/no-inference scan pattern for candidate feedback
  generation.
- Convert extracted impressions into `memory.feedback` items or pending
  workflow steps, not direct writes.
- Reuse the existing `memory/activator.py` principle: local retrieval creates
  candidates; AI can rank or select, but cannot invent executable targets.

## Patterns not to port now

| Reference area | Decision |
| --- | --- |
| Full A_Memorix host service | Too large for Plana Core. Plana already owns storage, recall, feedback, scope and relation modules. |
| ReAct memory retrieval loop | Plana's query planner and hybrid recall are smaller and safer for AstrBot plugin use. Borrow question planning only where needed. |
| Direct chat summarizer double-write | Plana should keep writes behind existing extractor/consolidator and workflow confirmation rules. |
| Large vector/graph runtime | Keep embedding and concept graph optional advisory layers. Do not make them execution prerequisites. |
| NetworkX hippocampus graph runtime | Plana already has concept/relation graph modules and SQLite storage; porting this would duplicate core memory authority. |
| Daily global accumulator as-is | Useful as inspiration for batch jobs, but Plana should use its existing consolidator and explicit maintenance/workflow triggers. |

## Plana landing plan

1. Web user-facing state:
   - Show memory totals, pending feedback, scope alias count, pending workflow
     confirmations and current risk in the top dashboard strip.
   - Status: implemented in this change.

2. Memory lifecycle metadata:
   - Add lifecycle fields or companion table for episodic/semantic/relation
     records: `active`, `protected_until`, `last_reinforced`,
     `inactive_since`, `restored_at`.
   - Add service methods for reinforce/protect/freeze/restore.
   - Require confirmation and audit for every lifecycle mutation.

3. Profile evidence and refresh:
   - Add profile snapshot/version table.
   - Add refresh queue with pending/running/failed/done states.
   - Add deterministic profile evidence buckets:
     `identity_settings`, `relationship_settings`, `stable_facts`,
     `interaction_preferences`, `recent_interactions`, `uncertain_notes`.
   - Keep profile injection participant-bound and capped by count/characters.
   - Surface pending and failed refreshes in Web.

4. Identity binding:
   - Add explicit account binding groups on top of existing identity and scope
     alias storage.
   - Binding and unbinding must use confirmation, verification code or admin
     action, and audit events.

5. Episode evidence chain:
   - Add lightweight episode records for consolidated summaries.
   - Link episodes to memory ids, semantic ids and relation ids.
   - Use episodes for explainable recall and profile evidence, not as an
     independent execution authority.

6. Candidate-only memory activation:
   - Ensure activator prompts can only choose from local candidate IDs.
   - Reject unknown IDs and fall back to deterministic top candidates when LLM
     output is invalid.

7. Relationship/profile scan:
   - Add a low-frequency scan mode that creates feedback candidates after
     thresholds and cooldowns.
   - Filter bot self and known unsafe sources.
   - Route all suggested memory/profile writes through confirmation.

## Safety boundary

- LLM retrieval and profile text remain advisory.
- Writes, deletes, lifecycle changes and binding changes require a confirmation
  boundary.
- Web may review and request actions, but storage/service layers perform the
  writes.
- External memory systems can be bridges later; Plana Core remains the source of
  policy, audit and confirmation.
- Direct auto-write scanners are not acceptable in Plana Core. They may produce
  candidates only.
