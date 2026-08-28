# Xiaowei Gallery Context Comparison — 2026-07-14

## Scope

- Source sample: C:/git/plana_qq_history_bootstrap/input/group_906678215_20260712_083826.json.
- Curated image-bearing windows: 24.
- The sample contains conversational reaction images and images produced by commands, generation, analysis, task progress, account recovery, or serious contexts.

## Result

- Xiaowei image-bearing windows: 24/24.
- Plana local Gallery allowed: 10/24.
- Context-reaction recall: 100.00%.
- Blocked-category false-positive rate: 0.00%.
- Direct media agreement with Xiaowei: 41.67%.
- Deliberate conservative divergences: 14.

Direct agreement is not the target: Xiaowei frequently attaches generated images, command result cards, OCR or analysis artifacts, and task-progress images. Plana Gallery only adopts the contextual reaction subset.

## Policy Notes

- Adopted signals: praise, laughter, speechlessness, surprise, doubt emoji, playful refusal, apology and light celebration.
- Rejected signals: API/code, OCR, download/report tasks, image generation/editing, restart/help commands, tokens, scoring, summaries, file operations, account risk, threats and appeals.
- This is a deterministic static gate regression; it does not invoke a model, Gallery writes, production tools or image delivery.

## Mismatches

- None.
