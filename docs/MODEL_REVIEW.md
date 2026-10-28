# Independent model-design review

Date: 2026-10-27. Reviewer: Model QA Specialist, task queuecraft_model_review. Read-only conceptual review; no model executions or dependency checks were performed.

Verdict: a compact CPU-trained operation ranker is a reasonable genuine-ML proposal, with quality and compute feasibility still unmeasured. A GNN/RL reproduction is not required for the first experiment.

## Findings integrated into the proposal

1. High: a global CP-SAT solution may not be representable by a restricted dispatcher. Specify action/schedule semantics and prove teacher-trace replay before training. Do not treat one optimal sequence as the only correct sequence.
2. High: state-level random splits leak whole-instance information. Split base instances first and keep variants/relabelings together. Exclude teacher outputs from model inputs.
3. Medium: next-action accuracy and FEASIBLE solver status cannot establish optimal schedule quality. Evaluate complete schedules, independent constraint checks, runtime, bounds and paired baseline results.

Minimum baselines include FIFO, shortest processing time and most work remaining. Explicitly report poor cases and training/teacher-generation costs. No guaranteed model win, confidence in optimality, or industrial validation belongs in the concepts.

The reviewer suggested known planned machine maintenance as a possible later extension. It is deliberately outside the first static makespan proposal; unexpected breakdown semantics are not defined or represented in the mockups.

## Primary references consulted by the reviewer

- https://proceedings.neurips.cc/paper/2020/hash/11958dfee29b6709f48a9ba0387a2431-Abstract.html
- https://developers.google.com/optimization/scheduling/job_shop
- https://developers.google.com/optimization/cp/cp_solver
- https://job-shop-lib.readthedocs.io/en/stable/api/job_shop_lib.dispatching.html
- https://job-shop-lib.readthedocs.io/en/stable/api/job_shop_lib.dispatching.rules.html
