# Memory Graph

`views/memory-graph.js` owns the dependency-free Canvas graph used by the memory view.

## Interaction Contract

- Keep the force-directed layout and real relation edges.
- Keep pointer-centered wheel zoom and drag-to-pan navigation.
- Keep adjacency focus on hover and persistent selection on click.
- Keep search targeting, reset, label controls, and keyboard navigation.
- Do not replace the graph with a static radial or circle layout during shell refactors.

The graph remains inline and iframe-safe. It must not add npm, CDN, or runtime frontend dependencies.
