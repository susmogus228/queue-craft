# QueueCraft 0.1.0 local implementation verification

Evidence date: 2026-10-28. Scope: selected Control Room design, complete initial static scheduling application, local API, trained CPU scorer, research evidence and documentation. GitHub publication and remote hosting are not part of this implementation step.

## Requirement reconciliation

| Requirement | Implemented evidence | Verification |
|---|---|---|
| Selected black Control Room | React UI, shared neutral/mint tokens, SVG schedule and inspector | Actual desktop and mobile screenshots; no generated design image is presented as a product screenshot |
| Genuine ML | Trained HGB operation ranker, 15 features, 18,242 labels | Three fits; fixed artifact hash/version; independent Model QA review |
| Compatible teacher | Offline serial job heads; CP-derived completion order | 18 pilot plus 240 training replay checks; no mismatch |
| Honest comparison | FIFO/SPT/MWKR/learned/CP-SAT, bounds and status | Independent schedule validator, paired frozen evidence, strong-baseline losses and runtime limitations visible |
| Input and editing | Three examples, strict JSON validation, duration and budget changes | Real browser recomputation; malformed/duplicate/oversized input checks; stale results blocked for replay |
| Inspect and replay | Keyboard-selectable operations, recorded feature step, manual/automatic replay, table alternative | Browser keyboard and reduced-motion journeys; CP-SAT has no fabricated decision trace |
| API | Documented asynchronous jobs, local static serving, cancellation/partial results | 38 transport tests; actual HTTP smoke; visible Swagger link exercised |
| Export and portability | Full provenance report and separate compact problem JSON | Download and actual file re-import; original input and solver budget preserved |
| Recovery and bounds | Bounded queue/storage, TTL cleanup, 404 and removed-run recovery | Regression tests plus browser fault simulations |
| Research and explanations | Sources, model card, results, uncertainty graph/CSV, screenshots | Model QA checked hashes, groups, split membership and saved paired calculations |

## Automated checks

- Python: `python -m pytest --basetemp work/pytest-review-green-20261028` passed 64 tests (38 transport, 17 core, 4 learning, 5 service). One installed Starlette/httpx deprecation warning remains; it did not fail tests.
- Frontend: `npm test` passed 12 tests; strict TypeScript and production Vite build passed. Final JS bundle is about 79 kB gzip.
- Browser: 28 main-flow checks and 13 review-regression checks passed. JSON records are in outputs/browser-qa-main.json and outputs/browser-qa-edge-cases.json. Main flow used actual computation; API failure/404/removal/unavailable-result cases were explicitly simulated at the browser response boundary.
- Actual DOM viewport checks: 1536×1024,390×844,320 px wide and 1024 px wide. No body overflow. The Gantt intentionally scrolls within its own container and provides a table alternative.
- Actual HTTP smoke confirms model readiness, five valid small-example schedules, CP-SAT optimum 11 and matching exported input. Its record is outputs/api-smoke.json.

## Independent reviews

Model QA Specialist: PASS WITH FINDINGS. It independently recomputed 396 canonical groups and checked model/data hashes, group disjointness 240/48/72/36, teacher/replay records and saved paired-result calculations. Findings concern honest strong-baseline/runtime/denominator presentation; the model card, results and UI record those limits. The reviewer did not refit or repeat frozen predictions.

Code Reviewer: initial NEEDS WORK, followed by PASS on a focused recheck. Root fixed all five findings: unavailable-run recovery, exported/stale solver budget, false feasible-result caption, feature-step provenance/stale candidates, and compact input portability. Idle TTL cleanup was also added. Regression tests were observed failing before the implementation fixes and passing afterward. The reviewer performed source review, not browser testing.

## Artifacts and display

docs/assets/control-room-desktop.png, control-room-mobile.png, research.png and api.png are actual screenshots. Earlier PNGs in docs/design/ are illustrative generated concepts. The evaluation PNG/SVG and CSV derive from saved measured JSON; rendering does not run the model.

Browser MCP restricts file output to its existing C: chat root. Temporary captures were written there and copied byte-for-byte into the D: project. A managed local terminal runs uvicorn on 127.0.0.1: 8774. An initial detached-process startup was rejected by automatic review; a managed foreground tool session succeeded without requesting elevated permissions or changing policy.

## Boundaries

This is a verified local research application, not factory-validated production control. No physical phone, assistive-technology screen reader, remote deployment or GitHub access was tested. Mobile evidence covers browser viewport behavior. The application uses synthetic static instances only; the scorer has no established advantage over FIFO/best-of-rules and is worse/slower than CP-SAT in the evaluated size range. No additional model fits were used to fix the UI.

The existing source graph did not contain QueueCraft. Source files were inspected directly; no indexing or graph completion is claimed. No unrelated project, global package installation or existing user data was modified.
