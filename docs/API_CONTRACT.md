# QueueCraft internal HTTP and service contract

All text/code is English. JSON machine indices are zero based, UI shows M1 for machine 0. Duration/start/end are integer abstract time units. Job IDs are safe short strings, operation IDs are `${job_id}.${index+1}`. Static fixed-machine, non-preemptive, no due dates.

## Instance

`{name: string, machines: integer, jobs: [{id: string, operations: [{machine: integer, duration: integer}]}]}`

Limits: name 1..80 trimmed characters; machines 1..12; jobs 1..24; safe unique IDs matching `[A-Za-z0-9_-]{1,24}`; operations per job 1..12; at most 144 operations total; integer duration 1..1000; integer machine 0..machines-1. Reject booleans, NaN, unknown fields and fractional numbers. Imported JSON max 128 KiB. A repeated machine within a job is legal. Domain validation uses these same limits.

## Endpoints

- GET /api/health: `{status: "ok", model_ready: boolean}`
- GET /api/model: root service `get_model_info()` result.
- GET /api/examples: `{examples: [instance, ...]}` from root service `list_examples()`.
- POST /api/runs: `{instance, strategies?: ["fifo","spt","mwkr","learned","cp_sat"], solver_seconds?: number}`; all methods default; unique nonempty strategies; solver budget 0.1..5 seconds. Returns HTTP 202 with a run snapshot.
- GET /api/runs/{id}: run snapshot.
- DELETE /api/runs/{id}: request cancellation for queued/running job; remove completed job; return a clear JSON state.
- GET /api/runs/{id}/export: JSON attachment of completed/partial results and original instance; reject unavailable results.
- /docs OpenAPI, /research source-backed research/model report; serve local web/dist at / when built.

Run snapshot: `{id, status, created_at, elapsed_seconds, instance, strategies, solver_seconds, results, error}`. status is queued/running/completed/failed/cancelled. elapsed_seconds is server elapsed wall time; no completion percentage is promised. Result methods are independent; preserve successful methods if a method fails. Max pending/retained jobs and expiry must be bounded. No imported instance is used for training or sent externally.

## Root Python integration

Module `queuecraft.service` exposes:

- `get_model_info() -> dict` with ready, version, feature_names, training_summary, evaluation, limitations; unready keeps baseline app usable.
- `list_examples() -> list[dict]`.
- `run_comparison(instance: dict, strategies: list[str], solver_seconds: float = 2.0, cancel_event: threading.Event | None = None) -> list[dict]`.

The API worker owns HTTP/schema/job management only. Root owns domain/model/comparison and validates again at the domain boundary. Workers must not create conflicting service/domain implementations.

## Method result

`{method, label, status, makespan, wall_seconds, best_bound, optimality_proven, operations, trace, validation, error}`

status: FEASIBLE/OPTIMAL/UNKNOWN/INFEASIBLE/MODEL_INVALID/UNAVAILABLE/CANCELLED/ERROR. Missing model produces UNAVAILABLE rather than fake ML output. Makespan/bound null when no schedule. Validation `{valid: boolean, errors: string[]}`.

Operation: `{id, job_id, index, machine, duration, start, end, step}`; index zero based. Step 1-based, for dispatch construction; reference schedule can use its own chronological display order and must be labeled as reference, not learned decisions.

Trace record: `{step, chosen_id, candidates: [{id, job_id, index, machine, duration, earliest_start, remaining_work, score, features}]}`. Scores are rank scores, not probabilities or confidence in optimality. CP-SAT need not supply trace; UI must distinguish reference schedule from dispatch replay. Candidate features are actual inputs; they are not causal explanations.

Frontend derives selected operation, Gantt coordinates and tables from operations/trace. Export/download uses actual run. Edited input invalidates old results (or shows explicit stale state) and never relabels old output as a recomputation.
