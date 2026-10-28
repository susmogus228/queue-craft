# QueueCraft: research and proposed direction

Research date: 2026-10-27. This document preserves the background research and original proposal. Implementation was approved on 2026-10-28; see RESULTS.md and the release verification for current measured evidence. No external benchmark download or GitHub publication has been performed.

## User problem

Several jobs compete for shared machines. Each job has an ordered list of operations. An operation requires one specified machine and a known processing duration. The planner wants every job finished sooner without breaking dependencies or running two operations on the same machine simultaneously.

This differs from RouteLab's routing task: the decisions here concern operation ordering and time on shared resources, rather than paths through a network.

## Existing approaches

| Reference | What the primary source documents | Consequence for QueueCraft |
|---|---|---|
| [frePPLe](https://frepple.com/docs/current/features.html) | Production scheduling, capacity constraints, scenario evaluation and an interactive Gantt plan editor. | A Gantt chart and capacity planning alone are established product capabilities. QueueCraft will have a much narrower scope than an ERP/APS product. No competitive quality claim has been tested. |
| [Google OR-Tools job shop](https://developers.google.com/optimization/scheduling/job_shop) | Precedence and no-overlap constraints, non-preemptive processing and makespan minimization using constraint programming. | Use an independent schedule validator and a mathematical reference with an explicit solver status and computational budget. A solver is not the learned model. |
| [JobShopLib](https://github.com/Pabloo22/job_shop_lib) | Dispatching rules, CP-SAT, random instances, benchmark loading, Gantt visualizations and learning environments. The repository identifies an MIT license. | Reuse proven concepts and evaluate library reuse before implementation. Do not present visualization, learned dispatching or step-by-step replay as globally novel. Dependency versions and benchmark redistribution terms still need verification before installation or bundling. |
| [Learning to Dispatch, NeurIPS 2020](https://proceedings.neurips.cc/paper/2020/hash/11958dfee29b6709f48a9ba0387a2431-Abstract.html) | Learns dispatch policies with graph representations and deep reinforcement learning. The paper reports a GPU-based training setup. | Learned scheduling is established research. A compact CPU-trained operation scorer is a more proportionate first experiment than promising a reproduction of the paper's GNN training. |
| [OR-Library](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/jobshopinfo.html) | A small collection of standard job-shop instances and instance-generation code, with source publications. | This topic does not require a huge audio/image dataset. Public availability does not by itself grant unrestricted redistribution. Preserve provenance and review terms before packaging external instances. |

The unavailable URL https://frepple.com/features/ returned CRAWL_NOT_FOUND. The current official documentation above was found and read instead. Repository documentation and paper sections were inspected; no running competitor applications or trained policies were tested.

## Proposed distinction

QueueCraft will be a local, reproducible scheduling comparison workbench:

1. Run FIFO, shortest-processing-time, most-work-remaining, a trained scorer and CP-SAT against the same instance.
2. Inspect a feasible schedule and replay the construction decisions of dispatch methods.
3. Select an operation and inspect its actual decision inputs. Feature values and model scores do not establish a causal explanation of optimality.
4. Change a known processing duration before execution and re-run every strategy on the revised problem.
5. Inspect wins, ties and losses across unseen instances, including poor model cases.

These are proposed product choices, not a claim of a new scheduling algorithm or superiority over existing tools.

## Genuine ML proposal

A small learned scorer ranks eligible operations using problem and partial-schedule features. Parameters are fitted on generated training instances and saved in a versioned artifact. This is supervised imitation/ranking, not reinforcement learning unless an actual reward-driven learning loop is later implemented.

Scikit-learn is a candidate CPU implementation. The exact estimator and installed API will be verified during implementation. No training duration, memory fit or quality improvement is guaranteed yet.

### Feasibility gate before model training

- Specify one schedule-generation mechanism, including ready-operation filtering and any permitted idle time.
- Ensure teacher traces can be reproduced by that mechanism. A full CP-SAT schedule is not automatically a valid next-action teacher.
- Preserve multiple equivalent good choices where appropriate; a different valid choice is not necessarily an error.
- If teacher replay fails, report the incompatibility before committing to the training target. Do not silently substitute a different learning task.

### Evaluation contract

- Split whole base instances before making training states. Keep each instance's perturbations and equivalent relabelings in one group.
- Fit preprocessing on training data only. Never use teacher start times, optimal cost or test outcomes as input features.
- Select parameters on validation instances; freeze the final test before tuning.
- Compare complete rollout schedules, not just next-action agreement with one teacher trace.
- Check every operation appears exactly once, job precedence, nonnegative start times and machine no-overlap independently of each solver.
- Report makespan, schedule construction time, feasibility, paired wins/ties/losses and poor-tail cases. Include model initialization/seeds where applicable.
- Compare against FIFO, SPT and most-work-remaining; a weak FIFO-only comparison is insufficient.
- Report CP-SAT status, time budget, incumbent and best bound. FEASIBLE is not a proof of optimality. Label a comparison as an optimality gap only when an optimum is established; otherwise show the relevant reference/bound explicitly.
- Keep training-data/teacher-generation compute separate from prediction time. Cap the initial pilot at three model configurations; establish the data/teacher budget after the feasibility gate.
- Treat generated/static benchmarks as controlled evidence, not validation on a real factory.

## Explicit first-release limits

Static single-site job-shop planning with known durations, fixed machine assignment and non-preemptive operations. Units are abstract time units unless an imported problem explicitly defines a real unit. The first target is makespan; due dates, setup times, stock, travel, staff shifts, energy and machine breakdowns are not modeled.

The duration-change comparison recomputes a plan before work starts. It does not simulate a surprise failure during an operation. Live plant integration, autonomous production control and a manufacturing digital twin are outside this initial proposal.

## Source access and claims

Sources were accessed on the research date through public official documentation, author repositories and a primary paper. No paid access, private recordings, external API keys or private operational records were used. No model or dataset was downloaded. Source links above support the background; the proposed product and ML design still require implementation and measurement.
