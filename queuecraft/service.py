"""Application use cases; scheduling and model loading stay out of HTTP code."""

from copy import deepcopy
from functools import lru_cache
import json
import logging

from threadpoolctl import threadpool_limits

from .domain import Instance
from .learning import ARTIFACTS, generate_instance, read_artifact
from .scheduling import FEATURE_NAMES, dispatch, empty_result, solve_cp


LOGGER = logging.getLogger(__name__)
LIMITATIONS = [
    "Experimental scorer trained on synthetic static job-shop problems, not real factory data.",
    "Fixed machine assignments and known integer durations; no deadlines, setups, faults or live production control.",
    "Rank scores are not probabilities or guarantees of optimality.",
    "The learned policy may lose to simple rules; inspect the paired evaluation and each actual schedule.",
    "Changing a duration replans before execution; no ongoing work is preserved.",
]


@lru_cache(maxsize=1)
def _model():
    return read_artifact()


def get_model_info():
    try:
        _, manifest = _model()
    except (OSError, ValueError, KeyError, ImportError) as exc:
        return {"ready": False, "version": None, "model_type": "CPU-trained operation ranker",
                "feature_names": list(FEATURE_NAMES), "training_summary": {}, "evaluation": {},
                "limitations": LIMITATIONS, "error": str(exc), "restart_required_after_training": True}
    evaluation = {}
    path = ARTIFACTS / "evaluation.json"
    if path.is_file():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report["model_sha256"] == manifest["sha256"]:
                evaluation = {name: report[name]["summary"] for name in ("test", "ood")}
        except (OSError, ValueError, KeyError):
            LOGGER.warning("Evaluation summary is unavailable or invalid")
    return {"ready": True, "version": manifest["version"], "model_type": manifest["model_type"],
            "feature_names": manifest["feature_names"], "training_summary": manifest["training_summary"],
            "evaluation": evaluation, "limitations": LIMITATIONS,
            "data_source": "Project-generated synthetic instances; whole-instance grouped splits",
            "target": "Negative normalized rollout regret; score is not a probability",
            "sklearn_version": manifest["sklearn_version"], "model_sha256": manifest["sha256"],
            "error": None, "restart_required_after_training": True}


def list_examples():
    small = {"name": "Small workshop", "machines": 3, "jobs": [
        {"id": "J1", "operations": [{"machine": 0, "duration": 3}, {"machine": 1, "duration": 2}, {"machine": 2, "duration": 2}]},
        {"id": "J2", "operations": [{"machine": 0, "duration": 2}, {"machine": 2, "duration": 1}, {"machine": 1, "duration": 4}]},
        {"id": "J3", "operations": [{"machine": 1, "duration": 4}, {"machine": 2, "duration": 3}]},
    ]}
    bottleneck = generate_instance(910001, 6, 4, "bottleneck")
    bottleneck["name"] = "Shared bottleneck / 6 jobs"
    long_tail = generate_instance(910002, 6, 5, "long_tail")
    long_tail["name"] = "Uneven operations / 6 jobs"
    return deepcopy([small, bottleneck, long_tail])


def run_comparison(instance, strategies, solver_seconds=2.0, cancel_event=None):
    problem = Instance.from_dict(instance)
    permitted = {"fifo", "spt", "mwkr", "learned", "cp_sat"}
    if not strategies or len(set(strategies)) != len(strategies) or any(method not in permitted for method in strategies):
        raise ValueError("Choose unique supported comparison strategies")
    scorer = None
    if "learned" in strategies:
        try:
            scorer, _ = _model()
        except (OSError, ValueError, KeyError, ImportError):
            pass
    results = []
    with threadpool_limits(limits=1):
        for method in strategies:
            if cancel_event is not None and cancel_event.is_set():
                results.append(empty_result(method, "CANCELLED"))
                break
            try:
                if method == "cp_sat":
                    result = solve_cp(problem, solver_seconds, cancel_event)
                else:
                    result = dispatch(problem, method, scorer, cancel_event)
            except Exception:
                LOGGER.exception("Strategy %s failed", method)
                result = empty_result(method, "ERROR", "This strategy failed; other results remain available.")
            results.append(result)
    return results
