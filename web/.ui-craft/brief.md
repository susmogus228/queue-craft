# QueueCraft Control Room

Approved reference: ../../docs/design/variant-2-control-room.png. Root specification: ../../docs/DESIGN_BRIEF.md and API_CONTRACT.md.

Build a charcoal engineering workbench with a narrow scenario/editor column, central real schedule and method comparison, and decision inspector. Use compact, legible system typography and monospaced numeric labels. Expose one useful next action in each empty/error state; avoid fabricated model metrics. The application starts from server-provided examples and displays only computed results.

Visual tokens live in src/styles.css: dark neutrals, one mint interaction accent, muted categorical job colors plus written IDs, 8px spacing grid, subtle borders, 4/6/8px radii, no decorative shadows. Desktop three-column layout collapses at content-driven breakpoints; the timeline and comparison scroll within their own regions. Reduced motion disables automatic replay. No animation dependency.
