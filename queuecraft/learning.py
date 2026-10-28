"""Synthetic grouped data, compatible teacher rollouts and CPU scoring artifacts."""

import hashlib
import itertools
import json
from pathlib import Path
import random

import numpy as np

from .domain import Instance
from .scheduling import FEATURE_NAMES, DispatchState, dispatch, replay_teacher, solve_cp


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def generate_instance(seed, jobs=4, machines=4, family="uniform"):
    rng = random.Random(seed)
    entries = []
    for j in range(jobs):
        order = list(range(machines))
        rng.shuffle(order)
        operations = []
        for machine in order:
            if family == "bottleneck":
                duration = rng.randint(18, 35) if machine == 0 else rng.randint(1, 12)
            elif family == "long_tail":
                duration = rng.randint(25, 60) if rng.random() < 0.2 else rng.randint(1, 8)
            else:
                duration = rng.randint(1, 20)
            operations.append({"machine": machine, "duration": duration})
        entries.append({"id": f"J{j + 1}", "operations": operations})
    return {"name": f"{family.replace('_', ' ').title()} {jobs}x{machines} / {seed}", "machines": machines, "jobs": entries}


def canonical_signature(data):
    """Exact grouping under job order/ID and machine relabelings up to six machines."""
    instance = Instance.from_dict(data)
    if instance.machines > 6:
        raise ValueError("Exact dataset canonicalization is limited to six machines")
    possibilities = []
    for permutation in itertools.permutations(range(instance.machines)):
        jobs = tuple(sorted(tuple((permutation[op.machine], op.duration) for op in job.operations) for job in instance.jobs))
        possibilities.append(jobs)
    canonical = (instance.machines, min(possibilities))
    return hashlib.sha256(repr(canonical).encode()).hexdigest()


def teacher_gate(count=18):
    cases = []
    for index in range(count):
        machines = 3 + index % 3
        instance = Instance.from_dict(generate_instance(800000 + index, machines + index % 2, machines))
        reference = solve_cp(instance, 0.5)
        if not reference["validation"]["valid"]:
            raise ValueError(f"Teacher returned no valid schedule for gate case {index}")
        replay = replay_teacher(instance, reference)
        cases.append({"instance": instance.name, "teacher_status": reference["status"],
                      "teacher_makespan": reference["makespan"], "replay_makespan": replay["makespan"]})
    return {"passed": True, "count": count, "semantics": "append-only serial generator; all unfinished job heads eligible for offline planning", "cases": cases}


def _finish_with_order(state, order):
    while state.remaining:
        candidates = state.candidates()
        chosen = min(candidates, key=lambda row: order[row["id"]])
        state.append(chosen, candidates)
    return max(row["end"] for row in state.operations)


def training_rows(instance, reference):
    """Regress negative rollout regret, allowing multiple equally good actions.

    The reference is used only for targets/completion order. It never enters
    the input features. A candidate's target uses a full legal completion after
    taking that candidate, not its resemblance to one arbitrary expert action.
    """
    replay = replay_teacher(instance, reference)
    order = {row["id"]: (row["start"], row["end"], row["id"]) for row in reference["operations"]}
    state = DispatchState(instance, record_trace=False)
    features, targets, weights = [], [], []
    steps = 0
    while state.remaining:
        candidates = state.candidates()
        costs = []
        for candidate in candidates:
            counterfactual = state.clone()
            counterfactual.append(candidate, candidates)
            costs.append(_finish_with_order(counterfactual, order))
        best = min(costs)
        for candidate, cost in zip(candidates, costs):
            features.append([candidate["features"][name] for name in FEATURE_NAMES])
            targets.append(-(cost - best) / instance.lower_bound)
            weights.append(1 / len(candidates))
        chosen_index = min(range(len(candidates)), key=lambda i: (costs[i], order[candidates[i]["id"]]))
        state.append(candidates[chosen_index], candidates)
        steps += 1
    return (np.asarray(features, dtype=np.float64), np.asarray(targets), np.asarray(weights) / steps,
            {"replay_valid": replay["validation"]["valid"], "replay_makespan": replay["makespan"],
             "teacher_makespan": reference["makespan"], "teacher_status": reference["status"],
             "label_rows": len(targets), "trajectory_makespan": max(row["end"] for row in state.operations)})


class LearnedScorer:
    def __init__(self, estimator):
        self.estimator = estimator

    def __call__(self, candidates):
        matrix = np.asarray([[row["features"][name] for name in FEATURE_NAMES] for row in candidates])
        return self.estimator.predict(matrix)


def read_artifact(directory=None):
    """Load only the fixed project-trained artifact, never a user-supplied model."""
    from importlib.metadata import version
    import joblib

    directory = Path(directory) if directory is not None else ARTIFACTS
    manifest_path = directory / "model.json"
    path = directory / "scorer.joblib"
    if not manifest_path.is_file() or not path.is_file():
        raise FileNotFoundError("The project-trained model artifact is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Model artifact checksum mismatch")
    if manifest["sklearn_version"] != version("scikit-learn") or manifest["feature_names"] != list(FEATURE_NAMES):
        raise ValueError("Model runtime or feature schema does not match this artifact")
    # joblib is trusted-code loading. The checksum detects corruption, not an
    # attacker able to replace both files. Only use this project's own artifact.
    estimator = joblib.load(path)
    return LearnedScorer(estimator), manifest


def build_splits(train_count=240, dev_count=48, test_count=72, ood_count=36):
    seen, records = set(), []
    specs = [("train", train_count, 10000), ("development", dev_count, 20000),
             ("test", test_count, 30000), ("ood", ood_count, 40000)]
    for split, count, base in specs:
        index = 0
        while sum(row["split"] == split for row in records) < count:
            seed = base + index
            machines = 3 + index % 3 if split != "ood" else 6
            jobs = machines + index % 2 if split != "ood" else 7
            family = ("uniform", "bottleneck", "long_tail")[(index // 3) % 3]
            instance = generate_instance(seed, jobs, machines, family)
            signature = canonical_signature(instance)
            index += 1
            if signature in seen:
                continue
            seen.add(signature)
            records.append({"split": split, "group": signature, "seed": seed,
                            "family": family, "instance": instance})
    return records
