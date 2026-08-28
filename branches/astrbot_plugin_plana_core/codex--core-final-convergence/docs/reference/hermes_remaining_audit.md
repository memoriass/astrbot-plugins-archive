# Hermes remaining audit

## Source

- Repository: `NousResearch/hermes-agent`
- Audited commit: `9259d1e`
- Date: 2026-06-25

## Conclusion

No high-value Hermes execution-governance item remains unabsorbed for the
current Plana Core phase.

The useful Hermes ideas have already been mapped into Plana:

- narrow toolset view per surface and advisor role
- proposal-only Workflow Center
- Core-side compiler, policy scan, confirmation and executor
- approval metadata, proposal hash and capability view hash drift guard
- external surface registry and default-deny Bridge workflow exposure
- skill-to-recipe adapter without importing an executable skill runtime
- sandbox posture wording without claiming in-process sandboxing
- Web risk review for policy, trace, write steps and posture

## Remaining Hermes ideas and decision

| Hermes area | Decision | Reason |
| --- | --- | --- |
| Terminal backend / OpenShell | Do not port now | AstrBot plugin should not expose shell execution. Keep only posture metadata and future sidecar protocol. |
| Multi-platform gateway | Do not port now | AstrBot already owns platform adapters. Plana only needs surface policy for command, Web, Bridge and LLM tool. |
| Public plugin market | Do not port now | Too much supply-chain surface. Keep local capability packs and Skill Center governance. |
| Full React dashboard | Borrow selectively | Useful for user-facing status, profile/scope banner, confirm dialogs and i18n. Avoid full Vite migration until AstrBot static asset path is settled. |
| Observer hooks | Defer as telemetry backlog | Plana already persists workflow policy, advisor trace, executor trace and audit state. A generic observer bus is useful later for tracing and export, but it is not blocking the current AstrBot-native secretary center. |
| Middleware hooks | Defer as extension backlog | Behavior-changing middleware is powerful, but it would widen the execution surface. Keep current workflow execution deterministic through Core compiler, policy scan and confirmation gates. |
| Memory provider abstraction | Defer to chat-memory audit | Hermes memory provider is generic and tool-oriented. Chat-memory and Maibot-style memory are more relevant for persona and user-specific long memory. |

## Next focus

Shift reference work from Hermes to chat-memory specialization:

- memory/persona separation
- user profile and relationship modeling
- memory activation and forgetting strategy
- memory quality feedback loop
- prompt-context budgeting for character-like assistants
