# QueueCraft Control Room Implementation Plan

> Execute within the approved design using test-driven core development and independent integration review. No Git publication or unrelated environment changes.

**Goal:** A usable local scheduling workbench with a genuinely trained CPU scorer, bounded API jobs, comparison and replay.

**Architecture:** Shared scheduling domain and independent validator; append-only serial schedule construction shared by heuristics and learned scorer; CP-SAT reference. A FastAPI service serves the built React UI and bounded temporary comparison jobs. Learning and frozen evaluation run separately from inference.

**Tech Stack:** Python, scikit-learn, OR-Tools, FastAPI/Pydantic, React/TypeScript/Vite, SVG.

**Spec:** docs/DESIGN_BRIEF.md, selected variant 2, docs/MODEL_REVIEW.md.

## Memory and agents

- Codex memory: reuse experimental split discipline; no old numeric results transfer.
- Codebase Memory: no indexed QueueCraft source project at initial preflight; source creation is now approved, indexing is not requested.
- Independent frontend: Frontend Developer owns web/ and its package metadata, implements selected layout and API contract, performs its typecheck/build.
- Independent HTTP/jobs surface: Backend Architect owns queuecraft/api.py and tests/test_api.py, consumes service contract, implements bounded jobs, validation and safe local serving.
- Shared domain/model/data: root exclusively owns queuecraft/domain.py, scheduling.py, learning.py, service.py, training commands, core tests and documentation.
- Independent review: Model QA Specialist reviews split/teacher/metric evidence after training; whole-product review and browser verification follow integration. Reviewers do not edit implementation.

## Review focus

- Teacher order may be unrepresentable by the dispatcher: prove replay before fitting.
- Whole-instance variants must not cross split boundaries.
- Missing artifact, invalid imports, job cancellation, timeout and partial method failure remain usable.
- Solver status and bounds must not overstate optimality; animation time is separate from inference time.
- Narrow viewports and keyboard users need access to schedule details and all controls.

## Tasks

- [x] 1. Define the contract and pin a project-local environment. Confirm APIs against installed versions and documentation.
- [x] 2. Write failing core tests; implement strict domain validation, schedule generator, baselines, CP-SAT and an independent schedule validator.
- [x] 3. Prove teacher replay on bounded training/development examples; record semantics and feasibility result.
- [x] 4. Generate grouped training/development/frozen evaluation instances. Fit up to three configurations, select using development complete rollouts, evaluate frozen test once, save artifacts/provenance/results.
- [x] 5. Implement HTTP jobs and model/example endpoints, meaningful API tests, bounded queue/cancellation/export/static serving.
- [x] 6. Implement selected Control Room interface: import/edit/compare/select/replay/export/research/API, real data, all failure states and responsive layout.
- [x] 7. Integrate, execute core/API/build checks, run browser desktop/mobile journeys, correct material failures, complete independent review.
- [x] 8. Document exact startup/training, real results, limitations and verification; leave the local app accessible. Do not publish without authorization.

## Rulings and evidence

The root project originally contains research/design files only. No Git worktree is needed to isolate an existing source checkout. New dependencies are installed only in this project's virtualenv/web directory. Training configuration remains the agreed small CPU scorer; input features use known static problem data and current partial schedule only.

Ruling: use a CP-derived forced-action rollout regret target and the shared offline serial generator. Eighteen pilot cases and all 240 training cases passed teacher replay. Three fits and development-only selection were completed; the frozen evaluation was scored once. No later UI fix changed the scorer or evaluation evidence.

Ruling: add compact problem saving beside full report export. Full traces can exceed the agreed 128 KiB import bound; compact saving preserves the input bound while supporting roundtrip portability.

Ruling: preserve solver budget in exported runs and invalidate the visible result when that budget changes. Add expired-run recovery and idle TTL cleanup after the independent review identified lifecycle gaps.

Browser evidence uses an isolated installed Edge process. The shared browser had a 75% zoom, so its requested viewport did not equal actual CSS dimensions. Final responsive checks assert the actual DOM viewport in the isolated browser. Browser-tool screenshot output is restricted to the existing C: chat directory; final artifacts are copied to this project's D: folders.
