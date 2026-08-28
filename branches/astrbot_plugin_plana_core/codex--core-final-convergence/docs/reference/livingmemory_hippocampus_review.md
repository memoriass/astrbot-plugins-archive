# LivingMemory and chat-memory hippocampus audit

## Source

- LivingMemory repository:
  `lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory`
- Audited commit: `d4392b6`
- Date: 2026-06-25

## Conclusion

LivingMemory is a high-value reference for Plana's Web memory visualization and
memory lifecycle ergonomics. The most useful part for the current Web stage is
not its full AstrBot Pages application, but its operator-facing graph view:
overview first, search/focus later, color-coded node types, and a side-channel
for memory details.

The chat-memory reference's hippocampus memory is also useful, but Plana should not port its
NetworkX runtime. Plana already has SQLite-backed concept graph, activation
spread, relation graph, recall and consolidation modules. The right adaptation
is to strengthen these existing modules and expose them better in Web.

LivingMemory is AGPL-licensed, so this project should borrow architecture and
interaction ideas only. Do not copy its implementation code.

## LivingMemory patterns worth adapting

| Area | What to borrow | Plana adaptation |
| --- | --- | --- |
| Web memory graph | A visual graph as the first view of memory state | Add a lightweight graph preview to the Concepts view using existing `/api/concepts` data. |
| Graph payload shape | `nodes`, `edges`, summary, matched IDs and top items | Keep Plana's current API for now; later add a richer `/api/memory-graph` payload if needed. |
| Large graph layout | Deterministic force-directed placement, viewport fit, hover/focus highlight, label collision checks | Plana now uses a compact bounded force solver, sorts by weight/degree, clips visible nodes/edges, avoids label overlap and redraws only on interaction or resize. |
| View modes | overview, query, memory-focus | Current stage implements overview only; query/focus can build on retrieval lab and concept search. |
| Node classes | topic/person/fact/summary colors | Plana Web now maps concept names to topic/person/fact/summary/other display classes. |
| Memory detail affordance | Graph plus list/detail surfaces | Plana Memories view now uses a list plus detail panel; graph visual remains above concept tables so details stay inspectable. |
| Lifecycle UI | status, importance and update history | Align with future memory lifecycle work: protect/freeze/restore/reinforce should be visible and confirmed. |
| Forgetting lifecycle | TTL, last accessed time, reinforcement count, active/expired/forgotten states | Worth adapting after a migration plan. Plana should layer it over current importance decay rather than replace storage abruptly. |

## Chat-memory hippocampus patterns worth adapting

| Area | What to borrow | Plana adaptation |
| --- | --- | --- |
| Memory graph as navigation model | Concepts and links make long-term memory easier to inspect | Continue enhancing `memory/graph.py` and Web graph view instead of adding a new graph runtime. |
| Similar concept merge | New concept names can merge into existing close concepts | Plana already has tokenizer similarity and `_SIMILAR_THRESHOLD`; keep improving explainability and Web visibility. |
| Activation spread | Nearby concepts can surface related memories | Plana already has `spread_activation`; expose activated neighbors in retrieval/debug views later. |
| LLM-assisted memory integration | Existing and new memory text can be merged | Keep optional integration callback, but route durable writes through confirmation where user-facing state changes. |
| Batch consolidation | Periodic condensation can create graph memories | Use Plana's existing consolidator and maintenance/workflow triggers, not the reference daily global accumulator. |

## Already landed

- Web Concepts view now includes a lightweight Canvas memory graph.
- The preview uses existing concept nodes and edges, so no new persistence or
  execution authority is introduced.
- Preview fixture data now contains a multi-node memory graph so the local Web
  preview shows the intended visual shape.
- The Canvas renderer is Plana-owned code: it borrows LivingMemory's interaction
  direction, but keeps implementation, data contract and dependency policy local.
- The Canvas renderer now handles larger graphs by ranking nodes with
  weight/degree, clipping visible graph size, running one bounded force-directed
  layout pass, checking label collisions and redrawing only on interaction or
  resize.
- Memories view now has a master-detail browser rather than a flat table.

## Not to port now

| Source | Decision |
| --- | --- |
| LivingMemory full Pages frontend | Too large for the current no-build Web shell. Keep the current embedded template until AstrBot static asset strategy is finalized. |
| LivingMemory force-directed Canvas implementation | Useful as a design reference; keep Plana's renderer self-owned so licensing, data shape and Web shell constraints remain controlled. |
| LivingMemory graph storage schema | Plana already has concept and relation storage; schema expansion should be incremental and migration-backed. |
| LivingMemory atom table as-is | The lifecycle model is useful, but Plana should not switch to atom storage directly. Add lifecycle fields/status to existing memories with migration and Web confirmation boundaries. |
| Reference NetworkX hippocampus | Duplicates Plana's storage-backed concept graph and complicates runtime dependencies. |
| Reference daily accumulator as-is | Too broad and too automatic; Plana should keep batch jobs explicit, observable and service-bound. |

## Next steps

1. Add a richer memory graph API:
   - summary counts
   - top nodes
   - top relations
   - matched IDs for retrieval/debug views

2. Add query/focus modes:
   - query mode can reuse retrieval lab input
   - focus mode can focus by memory ID or concept name
   - both must stay read-only

3. Add lifecycle overlays:
   - active/protected/frozen/restored display states
   - importance and last reinforced timestamps
   - confirmation-only actions for lifecycle mutations

4. Add LivingMemory-style forgetting in stages:
   - migration adds lifecycle status, last accessed, last reinforced, ttl days,
     expires at and reinforcement count to episodic memories
   - recall/touch updates last accessed only for selected hits
   - maintenance moves active memories to expired, then forgotten after a
     configured delay
   - deletion or hard cleanup remains confirmed and audited

5. Upgrade rendering only when needed:
   - keep the current Plana-owned Canvas compact
   - add query/focus controls and richer graph payloads before considering a
     larger rendering module
