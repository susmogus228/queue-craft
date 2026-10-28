"""Behavioral scheduling checks independent of HTTP and learned weights."""

from copy import deepcopy
import threading

import pytest

from queuecraft.domain import Instance, validate_schedule
from queuecraft.scheduling import dispatch, solve_cp, replay_teacher


def example():
    return {
        "name": "Small workshop", "machines": 3,
        "jobs": [
            {"id": "J1", "operations": [{"machine": 0, "duration": 3}, {"machine": 1, "duration": 2}, {"machine": 2, "duration": 2}]},
            {"id": "J2", "operations": [{"machine": 0, "duration": 2}, {"machine": 2, "duration": 1}, {"machine": 1, "duration": 4}]},
            {"id": "J3", "operations": [{"machine": 1, "duration": 4}, {"machine": 2, "duration": 3}]},
        ],
    }


@pytest.mark.parametrize("method", ["fifo", "spt", "mwkr"])
def test_baselines_schedule_every_operation_without_conflict(method):
    problem = Instance.from_dict(example())
    result = dispatch(problem, method)
    assert result["status"] == "FEASIBLE"
    assert result["validation"] == {"valid": True, "errors": []}
    assert len(result["operations"]) == 8
    assert len(result["trace"]) == 8
    assert result["makespan"] == max(op["end"] for op in result["operations"])
    assert not result["optimality_proven"]


def test_cp_proves_small_example_and_teacher_replay_preserves_cost():
    problem = Instance.from_dict(example())
    reference = solve_cp(problem, 2)
    assert reference["status"] == "OPTIMAL"
    assert reference["makespan"] == 11
    assert reference["best_bound"] == 11
    replay = replay_teacher(problem, reference)
    assert replay["validation"]["valid"]
    assert replay["makespan"] <= reference["makespan"]
    assert len(replay["trace"]) == 8


def test_validator_rejects_overlap_duplicate_missing_and_wrong_duration():
    problem = Instance.from_dict(example())
    good = dispatch(problem, "fifo")["operations"]
    overlap = deepcopy(good)
    for operation in overlap:
        operation["start"] = 0
        operation["end"] = operation["duration"]
    assert not validate_schedule(problem, overlap)["valid"]
    assert not validate_schedule(problem, good[:-1])["valid"]
    assert not validate_schedule(problem, good + [good[0]])["valid"]
    changed = deepcopy(good)
    changed[0]["duration"] += 1
    assert not validate_schedule(problem, changed)["valid"]


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(machines=True),
    lambda d: d.update(machines=0),
    lambda d: d.update(extra="ignored?"),
    lambda d: d["jobs"][0]["operations"][0].update(duration=1.5),
    lambda d: d["jobs"][0]["operations"][0].update(duration=True),
    lambda d: d["jobs"][0]["operations"][0].update(machine=3),
    lambda d: d["jobs"][1].update(id="J1"),
    lambda d: d["jobs"][0].update(id="unsafe/id"),
    lambda d: d.update(jobs=[]),
])
def test_domain_rejects_invalid_or_ambiguous_inputs(mutate):
    payload = example()
    mutate(payload)
    with pytest.raises(ValueError):
        Instance.from_dict(payload)


def test_repeated_machine_is_legal_and_independent_jobs_can_start_together():
    problem = Instance.from_dict({"name": "Repeated", "machines": 2, "jobs": [
        {"id": "A", "operations": [{"machine": 0, "duration": 2}, {"machine": 0, "duration": 1}]},
        {"id": "B", "operations": [{"machine": 1, "duration": 2}]},
    ]})
    result = dispatch(problem, "spt")
    assert result["validation"]["valid"]
    assert sum(op["start"] == 0 for op in result["operations"]) == 2
    assert result["makespan"] == 3


def test_cancellation_does_not_return_fake_completed_schedule():
    event = threading.Event()
    event.set()
    assert dispatch(Instance.from_dict(example()), "fifo", cancel_event=event)["status"] == "CANCELLED"
    assert solve_cp(Instance.from_dict(example()), 1, cancel_event=event)["status"] == "CANCELLED"


def test_maximum_domain_budget_and_empty_name_are_rejected():
    payload = example()
    payload["name"] = " "
    with pytest.raises(ValueError):
        Instance.from_dict(payload)
    payload = example()
    payload["jobs"] = [{"id": f"J{i}", "operations": [{"machine": 0, "duration": 1}] * 12} for i in range(13)]
    with pytest.raises(ValueError):
        Instance.from_dict(payload)
