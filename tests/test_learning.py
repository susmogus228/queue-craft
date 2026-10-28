"""Leakage, teacher compatibility and unavailable-model behavior."""

from copy import deepcopy
import math

import numpy as np

from queuecraft.domain import Instance
from queuecraft.learning import canonical_signature, generate_instance, training_rows, teacher_gate
from queuecraft.scheduling import FEATURE_NAMES, dispatch, solve_cp


def test_canonical_groups_job_and_machine_relabelings():
    original = generate_instance(123, 4, 3)
    renamed = deepcopy(original)
    renamed["name"] = "Renamed"
    renamed["jobs"].reverse()
    permutation = [2, 0, 1]
    for index, job in enumerate(renamed["jobs"]):
        job["id"] = f"Renamed{index}"
        for op in job["operations"]:
            op["machine"] = permutation[op["machine"]]
    assert canonical_signature(original) == canonical_signature(renamed)
    renamed["jobs"][0]["operations"][0]["duration"] += 1
    assert canonical_signature(original) != canonical_signature(renamed)


def test_training_targets_are_finite_and_do_not_enter_features():
    instance = Instance.from_dict(generate_instance(989, 3, 3))
    teacher = solve_cp(instance, 1)
    x, y, weights, evidence = training_rows(instance, teacher)
    assert x.shape[1] == len(FEATURE_NAMES)
    assert len(x) == len(y) == len(weights)
    assert np.isfinite(x).all() and np.isfinite(y).all()
    assert np.max(y) <= 1e-12
    assert (weights > 0).all()
    assert evidence["replay_valid"]
    assert evidence["replay_makespan"] <= teacher["makespan"]
    assert not any("teacher" in key or "optimal" in key for key in FEATURE_NAMES)


def test_gate_covers_multiple_sizes_and_passes_before_fit():
    report = teacher_gate(count=6)
    assert report["passed"]
    assert report["count"] == 6
    assert all(item["replay_makespan"] <= item["teacher_makespan"] for item in report["cases"])


def test_missing_model_is_explicit_and_learned_scores_are_not_probabilities():
    instance = Instance.from_dict(generate_instance(2, 3, 3))
    missing = dispatch(instance, "learned")
    assert missing["status"] == "UNAVAILABLE" and missing["makespan"] is None
    result = dispatch(instance, "learned", scorer=lambda rows: [-row["duration"] for row in rows])
    assert result["validation"]["valid"]
    assert all(math.isfinite(row["score"]) for step in result["trace"] for row in step["candidates"])
    assert all(row["score"] < 0 for step in result["trace"] for row in step["candidates"])
