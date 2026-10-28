"""User-facing services run actual scheduling, without the HTTP transport."""

from copy import deepcopy
import threading

from queuecraft import service


def test_examples_are_independent_and_have_actual_valid_baseline_schedules():
    examples = service.list_examples()
    original_name = examples[0]["name"]
    examples[0]["name"] = "Changed"
    assert service.list_examples()[0]["name"] == original_name
    for instance in service.list_examples():
        results = service.run_comparison(instance, ["fifo", "spt", "mwkr", "cp_sat"], 0.2)
        assert len(results) == 4
        assert all(row["validation"]["valid"] for row in results)


def test_missing_model_does_not_hide_real_baselines(monkeypatch):
    def unavailable():
        raise FileNotFoundError("Missing model")
    monkeypatch.setattr(service, "_model", unavailable)
    info = service.get_model_info()
    assert not info["ready"]
    results = service.run_comparison(service.list_examples()[0], ["spt", "learned", "cp_sat"])
    assert results[0]["makespan"] is not None
    assert results[1]["status"] == "UNAVAILABLE"
    assert results[2]["makespan"] == 11


def test_duration_edit_is_recomputed_and_inputs_are_not_mutated():
    before = service.list_examples()[0]
    after = deepcopy(before)
    after["jobs"][0]["operations"][0]["duration"] = 30
    old = service.run_comparison(before, ["spt"])[0]
    new = service.run_comparison(after, ["spt"])[0]
    assert old["makespan"] != new["makespan"]
    assert before["jobs"][0]["operations"][0]["duration"] == 3
    assert new["validation"]["valid"]


def test_strategy_failure_is_contained(monkeypatch):
    original = service.dispatch
    def one_failure(instance, method, *args, **kwargs):
        if method == "fifo":
            raise RuntimeError("Internal details should stay in logs")
        return original(instance, method, *args, **kwargs)
    monkeypatch.setattr(service, "dispatch", one_failure)
    results = service.run_comparison(service.list_examples()[0], ["fifo", "spt"])
    assert results[0]["status"] == "ERROR"
    assert "Internal details" not in results[0]["error"]
    assert results[1]["validation"]["valid"]


def test_cancelled_comparison_is_not_silently_completed():
    event = threading.Event()
    event.set()
    results = service.run_comparison(service.list_examples()[0], ["spt", "cp_sat"], cancel_event=event)
    assert results[0]["status"] == "CANCELLED"
