# QueueCraft: interface and implementation proposal

Status: variant 2 (Control Room) was selected for implementation on 2026-10-28. This document records the approved scope and original concept constraints. Current model evidence is in RESULTS.md; application verification is recorded separately.

## Output and stack

- Project root: the repository root.
- Current outputs: research, a design brief, a methodological review, generation prompts and three PNG interface concepts.
- Proposed frontend: React, TypeScript and Vite; SVG for inspectable Gantt bars and lightweight graph/flow diagrams. Native controls and a small shared component system before additional UI libraries.
- Proposed backend: local Python/FastAPI, validated JSON inputs and one bounded solve job at a time.
- Proposed learning: compact scikit-learn scorer, with a separately reproducible training command and saved artifact.
- Proposed reference: OR-Tools CP-SAT, subject to dependency/version verification. JobShopLib reuse will be assessed rather than automatically installed.
- Rationale: local CPU execution, inspectable schedules, small tabular model and explicit scheduling constraints. GPU-dependent training is not part of the proposal.

## Three visual directions

1. Workshop: light, restrained cobalt, clear input-to-plan layout. Easiest first-use experience.
2. Control Room: charcoal, mint accent, aligned timeline and decision inspector. Expanded comparison without decorative dashboards.
3. Planning Desk: warm paper, orange accent, machine flow and operation editor alongside a schedule. Emphasizes understanding and changing a scenario.

All concepts share the same feasible product scope. Their different layouts do not authorize extra backend features. English UI, 8px spacing grid, maximum two font families, restrained corners, consistent outline icons, semantic categorical job colors with written IDs.

## Demonstration state in the images

All images are AI-generated static UI concepts. No image is a screenshot of a running application. Diagrams and numbers are illustrative. Comparison results are blank and marked not run; model status is not trained. These images cannot establish Gantt correctness, responsive behavior or measured performance.

Use a small three-job, three-machine, eight-operation example adapted from the official OR-Tools introduction. Job order: J1=M1(3),M2(2),M3(2); J2=M1(2),M3(1),M2(4); J3=M2(4),M3(3). A reference drawing can show M1:J1.1[0,3],J2.1[3,5]; M2:J3.1[0,4],J1.2[4,6],J2.3[6,10]; M3:J2.2[5,6],J3.2[6,9],J1.3[9,11]. This is a source-derived illustration, not a locally computed benchmark or a learned-model result. Raster generation may not place every bar precisely; implementation must derive positions from validated schedule data.

## Core user journey

Choose an example or import a small JSON instance. Inspect jobs, operation ordering and durations. Run a strategy comparison. Inspect schedule constraints and solver status. Replay dispatch decisions; select an operation to inspect its features. Change a processing duration and recompute the same strategies. Export the actual schedule and the comparison report.

The replay displays saved construction steps. Its animation speed is separate from measured solver/inference time. Do not imply physical time passes while a backend computes a plan.

## API approach (proposal, not implemented)

- POST /api/runs: validated instance, strategy set and explicit solver budget.
- GET /api/runs/{id}: queued/running/completed/failed/cancelled state, results, bounds and timings.
- DELETE /api/runs/{id}: cancel or remove a temporary run.
- GET /api/runs/{id}/export: completed schedule/report, with provenance.
- GET /api/model: actual artifact readiness, version, training-data provenance and evaluation summary.
- /docs: visible OpenAPI reference.

Same-origin local requests; no paid AI API or account required. No automatic training from imported jobs. Bind locally by default; remote deployment and public GitHub publishing require their own agreed step. GitHub stores the project; a server is needed for Python computation.

## Required implementation states and accessibility

Empty input offers an example and JSON import. Invalid schema identifies the affected job/operation. Show missing model explicitly and allow baseline comparisons. Queued/running states have elapsed time and cancellation; do not invent completion percentages. Preserve partial successful strategies when another fails or times out. Distinguish solver UNKNOWN, INFEASIBLE, MODEL_INVALID, FEASIBLE and OPTIMAL without turning a timeout into an impossibility claim. Disable export until its artifact exists.

Include keyboard selection and a table alternative to Gantt, visible focus, written job IDs, accessible tooltips, reduced-motion replay and no reliance on color alone. On narrow screens stack the inspector, preserve usable timeline scrolling and keep controls reachable. Static desktop concepts do not count as mobile verification.

## Memory and agents

Codex memory: prior experimental discipline informs split boundaries and honest claims; no prior numeric result transfers to this project. Codebase Memory: fresh list_projects did not contain QueueCraft, and the project path did not exist before this work. No indexing was requested or performed.

Root owns research, requirements, images and source/prompt records. Model QA Specialist independently reviewed ML feasibility and evaluation read-only; its findings constrain this proposal. There are no parallel implementation owners.

## Completion boundary for this phase

Deliver cited analogue research, a feasible ML proposal, three distinct saved interface concepts and the reviewer findings. Ask the user to choose a layout before implementation. Do not call the application or model complete.
