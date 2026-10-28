# Independent review resolution

Date: 2026-10-28.

## Model QA

PASS WITH FINDINGS: genuine supervised fitted ranker, no blocking feature/split leakage or paired-calculation error found. Reviewer verified all 396 canonical groups, hashes, 240 optimal training teachers and saved evaluation results without new predictions or fits.

Required presentation fixes: show FIFO and best-of-rules alongside SPT/MWKR; report that CP-SAT was better and faster; state exact offline-rule semantics; show 35/36 CP coverage on the larger-size set; distinguish forced-action rollout regret from true optimal action cost. These appear in RESULTS.md, MODEL_CARD.md, README and the Research UI.

## Implementation review

Initial verdict: NEEDS WORK. Follow-up verdict: PASS for the corrected source surfaces.

| Finding | Resolution | Evidence |
|---|---|---|
| 404 polling and DELETE/removed could lock the UI | Preserve HTTP status, recover/reset unavailable runs, handle removed directly | HTTP error unit test plus actual UI response-boundary simulations |
| Budget absent from provenance and stale checks | Snapshot/export solver_seconds; include budget in stale check and display | Python RED→GREEN and UI budget-change check |
| Missing result claimed feasible | Gate description on nonempty operations and valid schedule | Unit test plus simulated unavailable result in browser |
| Inspector mixed decision steps and stale candidate scores | Explicit recordedDecision source step; hide stale candidates | Unit test and browser provenance/stale checks |
| Large trace report cannot satisfy small input limit | Separate compact Save problem | Downloaded file imported directly; actual large report was 350,696 bytes |
| Idle TTL retained data until next request | Periodic worker cleanup | Python RED→GREEN idle-retention test |

Root also fixed the actual export envelope importer and raw duplicate-key ambiguity before final browser verification. The final automated suite has 64 Python and 12 frontend tests; all 41 recorded browser checks passed.
