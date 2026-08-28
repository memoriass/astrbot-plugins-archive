# Retirement Notice

Plana Skill Center was retired on 2026-07-21.

## Runtime Status

- The AstrBot entrypoint is an inert compatibility shell.
- No commands, Web APIs, LLM tools, services, scans, approvals, exports, or background work are registered or started.
- The retired entrypoint does not initialize SQLite or create data and export directories.
- Existing databases, quarantined drafts, approved exports, manifests, and repository files are not deleted or rewritten.

## Replacement

Supported skill and capability candidate governance now belongs to the controlled in-process workflows in Plana Core. Core remains responsible for allowed candidate sources, review, confirmation, promotion, and execution boundaries.

New deployments must not depend on the historical `/plana_skill_center/*` endpoints, `/plana-skill` command, or `plana_skill_propose` tool.

## Repository Policy

The historical scanner, store, manager, contracts, and export helpers remain for audit and data interpretation. Retirement does not rename the repository or migrate stored data.
