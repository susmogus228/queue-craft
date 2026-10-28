# QueueCraft scorer 0.1.0

## Intended use

An inspectable research policy for static job-shop scheduling. The scorer ranks the next eligible operation during offline construction. Use it alongside the included rules and mathematical reference; inspect schedule validity and measured losses. No production-control or factory-savings claim is supported.

## Model and target

HistGradientBoostingRegressor, scikit-learn 1.9.1. Selected configuration: 180 iterations, maximum 15 leaves, minimum 25 samples/leaf, L 2=2.0, learning rate 0.08, seed 47, no internal early-stopping split. Three candidate configurations were fitted; selection used complete rollouts on 48 development instances. Selection did not use the frozen test or larger-size set.

Target: negative normalized forced-action rollout regret with a CP-derived completion order. For each state, the label generator forces each eligible candidate, completes a legal schedule using the reference ordering and compares its makespan with the best candidate completion in that state. Equal outcomes share targets. This target is not a proof of each action's true optimal cost-to-go. The method is supervised learning, not reinforcement learning.

## Features

Known static problem data and current partial schedule supply 15 numeric inputs: duration, remaining job work, successor work, earliest start/finish, job-ready time, machine-ready time, remaining machine workload, job progress, total remaining fraction, machine wait, job wait, job count, machine count and machine busy fraction. Work/time features normalize by an input-only lower bound; fractions/counts use the definitions in scheduling.py.

Teacher start times, optimum, rollout labels, IDs and frozen-test outcomes are not model inputs. Job IDs affect deterministic tie-breaking, not the learned feature vector.

## Data

Project-generated integer-duration instances, three families: uniform durations, a machine bottleneck and long-tail durations. Training/development/test include 3–6 jobs and 3–5 machines; larger-size checks use 7 jobs and 6 machines with the same duration families. All 396 groups are unique under exact job order/ID and machine relabeling canonicalization. Split counts 240/48/72/36; split before decision-state construction. No user imports or private operational data are included.

The training set produced 18,242 candidate labels. All 240 CP teachers proved optimal in their 0.4-second budget and passed replay; an earlier 18-case pilot verified compatibility. Each candidate completion remains constrained by the shared schedule generator. Teacher solves use one worker and seed 42.

## Evaluation and limitations

See [all measured comparisons](RESULTS.md). The frozen test supports a mean reduction against this SPT and MWKR implementation. It does not establish superiority over FIFO or the per-instance best rule. CP-SAT is better and faster in this size range. One of 36 larger CP solves returned UNKNOWN in 0.5 seconds; its missing incumbent is not fabricated or treated as infeasible.

Confidence intervals bootstrap paired instances conditional on the selected artifact. They do not include training-seed variation. Different candidate hyperparameters and seeds do not form a controlled seed-stability study. No real-factory dataset, online adaptation, unexpected faults, deadlines, shifts, material constraints or perceptual/human evaluation are represented.

## Artifact handling

Model/data SHA-256 values, package version, exact features, configuration selection and training evidence are stored beside the artifact. The application rejects incompatible versions, schemas or a checksum mismatch. Joblib can execute code when loading; only this project's locally generated trusted artifact belongs in that path. Imported JSON cannot replace weights. The application never trains during inference.

## Independent review

Model QA Specialist independently recomputed all 396 canonical groups and verified split membership, hashes, saved teacher/replay evidence and paired aggregate calculations. It found no blocking leakage or metric error. Its findings require displaying FIFO/best-of-rules losses, precise rule semantics, missing-reference denominators and the lack of solver-speed advantage. The review did not run new fits or repeat frozen predictions.
