"""Bounded CPU experiment: gate, fit three candidates, evaluate frozen sets once."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from .domain import Instance
from .learning import ARTIFACTS, ROOT, LearnedScorer, build_splits, read_artifact, teacher_gate, training_rows
from .scheduling import FEATURE_NAMES, dispatch, solve_cp

DATA_PATH = ROOT / "data" / "instances.json"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def score_instances(records, scorer, include_reference=False):
    values = []
    for record in records:
        instance = Instance.from_dict(record["instance"])
        methods = {method: dispatch(instance, method, scorer=scorer if method == "learned" else None, record_trace=False)
                   for method in ("fifo", "spt", "mwkr", "learned")}
        if include_reference:
            methods["cp_sat"] = solve_cp(instance, 0.5)
        if not all(row["validation"]["valid"] for row in methods.values() if row["makespan"] is not None):
            raise ValueError("Evaluation encountered an invalid schedule")
        values.append({"group": record["group"], "family": record["family"], "name": instance.name,
                       "jobs": len(instance.jobs), "machines": instance.machines,
                       "input_lower_bound": instance.lower_bound,
                       "methods": {method: {key: result[key] for key in ("status", "makespan", "wall_seconds", "best_bound", "optimality_proven", "validation")}
                                   for method, result in methods.items()}})
    return values


def summarize(values):
    result = {"count": len(values), "methods": {}, "paired": {}}
    for method in ("fifo", "spt", "mwkr", "learned", "cp_sat"):
        rows = [item["methods"][method] for item in values if method in item["methods"]]
        if not rows:
            continue
        valid = [row for row in rows if row["makespan"] is not None and row["validation"]["valid"]]
        result["methods"][method] = {
            "valid_count": len(valid), "optimal_count": sum(row["optimality_proven"] for row in valid),
            "mean_makespan": float(np.mean([row["makespan"] for row in valid])) if valid else None,
            "median_wall_ms": float(np.median([row["wall_seconds"] * 1000 for row in rows])),
        }
    rng = np.random.default_rng(20261028)
    for baseline in ("fifo", "spt", "mwkr", "best_of_rules", "cp_sat"):
        pairs = []
        for item in values:
            outcomes = item["methods"]
            if baseline == "best_of_rules":
                reference = min(outcomes[key]["makespan"] for key in ("fifo", "spt", "mwkr"))
            elif baseline not in outcomes or outcomes[baseline]["makespan"] is None:
                continue
            else:
                reference = outcomes[baseline]["makespan"]
            pairs.append((outcomes["learned"]["makespan"], reference))
        if not pairs:
            continue
        relative = np.asarray([(baseline_cost - learned) / baseline_cost * 100 for learned, baseline_cost in pairs])
        bootstrap = np.mean(relative[rng.integers(0, len(relative), size=(1000, len(relative)))], axis=1)
        result["paired"][baseline] = {
            "count": len(pairs), "wins": sum(a < b for a, b in pairs), "ties": sum(a == b for a, b in pairs),
            "losses": sum(a > b for a, b in pairs), "mean_improvement_percent": float(np.mean(relative)),
            "median_improvement_percent": float(np.median(relative)),
            "worst_improvement_percent": float(np.min(relative)),
            "mean_improvement_ci95_percent": [float(value) for value in np.percentile(bootstrap, [2.5, 97.5])],
        }
    return result


def train():
    if (ARTIFACTS / "model.json").exists():
        raise SystemExit("An artifact already exists. Preserve it; create a new explicit experiment before training again.")
    started = time.perf_counter()
    gate = teacher_gate()
    save(ARTIFACTS / "teacher_gate.json", gate)
    print(f"Teacher replay gate: {gate['count']} / {gate['count']} passed", flush=True)
    records = build_splits()
    save(DATA_PATH, records)
    data_sha = hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()
    configs = [
        {"max_iter": 80, "max_leaf_nodes": 7, "min_samples_leaf": 15, "l2_regularization": 0.5, "random_state": 11},
        {"max_iter": 140, "max_leaf_nodes": 15, "min_samples_leaf": 20, "l2_regularization": 1.0, "random_state": 23},
        {"max_iter": 180, "max_leaf_nodes": 15, "min_samples_leaf": 25, "l2_regularization": 2.0, "random_state": 47},
    ]
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "data_sha256": data_sha,
                "splits": {name: [row["group"] for row in records if row["split"] == name] for name in ("train", "development", "test", "ood")},
                "configs": configs, "teacher_budget_seconds_per_instance": 0.4,
                "evaluation_reference_budget_seconds": 0.5, "fits_limit": 3,
                "selection": "lowest development mean makespan ratio to per-instance best of FIFO/SPT/MWKR; ties prefer earlier configuration",
                "target": "negative normalized forced-action rollout regret using a CP-derived completion order",
                "ci_scope": "paired evaluation instances conditional on one selected trained artifact; not training-seed uncertainty"}
    save(ARTIFACTS / "protocol.json", protocol)
    train_records = [row for row in records if row["split"] == "train"]
    dev_records = [row for row in records if row["split"] == "development"]
    xs, ys, ws, teachers = [], [], [], []
    label_started = time.perf_counter()
    for index, record in enumerate(train_records, 1):
        instance = Instance.from_dict(record["instance"])
        reference = solve_cp(instance, 0.4)
        if not reference["validation"]["valid"]:
            raise ValueError("A training teacher did not produce a feasible plan; no silent replacement is allowed")
        x, y, weights, evidence = training_rows(instance, reference)
        xs.append(x)
        ys.append(y)
        ws.append(weights)
        teachers.append({"group": record["group"], **evidence})
        if index % 30 == 0:
            print(f"Labeled {index}/{len(train_records)} training instances", flush=True)
    x, y, weights = np.vstack(xs), np.concatenate(ys), np.concatenate(ws)
    label_seconds = time.perf_counter() - label_started
    save(ARTIFACTS / "training_evidence.json", {"rows": len(y), "features": list(FEATURE_NAMES), "teacher_instances": teachers,
                                               "teacher_generation_and_label_seconds": label_seconds})
    candidates, best_model, best_index, best_score = [], None, None, float("inf")
    for index, config in enumerate(configs):
        model = HistGradientBoostingRegressor(learning_rate=0.08, early_stopping=False, **config)
        fit_started = time.perf_counter()
        model.fit(x, y, sample_weight=weights)
        fit_seconds = time.perf_counter() - fit_started
        values = score_instances(dev_records, LearnedScorer(model))
        score = float(np.mean([item["methods"]["learned"]["makespan"] / min(item["methods"][key]["makespan"] for key in ("fifo", "spt", "mwkr")) for item in values]))
        candidates.append({"index": index, "config": config, "fit_seconds": fit_seconds,
                           "development_selection_ratio": score, "development": summarize(values)})
        print(f"Fit {index + 1}/3: development ratio {score:.4f}, fit {fit_seconds:.2f}s", flush=True)
        if score < best_score:
            best_model, best_index, best_score = model, index, score
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / "scorer.joblib"
    joblib.dump(best_model, path, compress=3)
    manifest = {"ready": True, "version": "0.1.0", "model_type": "HistGradientBoostingRegressor operation ranker",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "sklearn_version": version("scikit-learn"),
                "feature_names": list(FEATURE_NAMES), "selected_configuration": best_index,
                "data_sha256": data_sha, "training_summary": {"instances": len(train_records), "development_instances": len(dev_records),
                    "label_rows": len(y), "fits": len(configs), "teacher_optimal_count": sum(row["teacher_status"] == "OPTIMAL" for row in teachers),
                    "teacher_replay_pass_count": len(teachers), "teacher_and_label_seconds": label_seconds,
                    "total_training_seconds": time.perf_counter() - started},
                "candidates": candidates, "created_at": datetime.now(timezone.utc).isoformat()}
    save(ARTIFACTS / "model.json", manifest)
    print(f"Saved model configuration {best_index + 1}; frozen evaluation has not been used.", flush=True)


def evaluate():
    path = ARTIFACTS / "evaluation.json"
    if path.exists():
        raise SystemExit("Frozen evaluation already exists. Do not tune against or overwrite it.")
    records_path = DATA_PATH
    records = json.loads(records_path.read_text(encoding="utf-8"))
    protocol = json.loads((ARTIFACTS / "protocol.json").read_text(encoding="utf-8"))
    if hashlib.sha256(records_path.read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise ValueError("Frozen dataset checksum mismatch")
    groups = [row["group"] for row in records]
    if len(groups) != len(set(groups)):
        raise ValueError("Instance groups overlap")
    scorer, manifest = read_artifact(ARTIFACTS)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "model_sha256": manifest["sha256"],
              "data_sha256": protocol["data_sha256"], "units": "abstract time units", "real_factory_validation": False,
              "note": "Positive improvement means lower makespan. Best-of-rules is a per-instance oracle, not a separately trained baseline. CP-SAT comparisons are to its returned incumbent; check optimality_proven per instance.",
              "limitations": ["Synthetic static instances only", "No release dates, setups, maintenance, deadlines or unexpected faults",
                              "One selected artifact; training-seed uncertainty not assessed", "No guarantee of improvement on an imported problem"]}
    for split in ("test", "ood"):
        values = score_instances([row for row in records if row["split"] == split], scorer, True)
        report[split] = {"summary": summarize(values), "instances": values}
        print(f"{split}: {json.dumps(report[split]['summary']['paired'])}", flush=True)
    save(path, report)
    print("Frozen evaluation saved. No model selection or retraining was performed on these results.", flush=True)


def main():
    global ARTIFACTS, DATA_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["gate", "train", "evaluate"])
    parser.add_argument("--run-dir", type=Path, help="Separate reproduction directory; does not activate or overwrite the shipped model")
    args = parser.parse_args()
    if args.run_dir is not None:
        directory = args.run_dir.resolve()
        ARTIFACTS = directory / "artifacts"
        DATA_PATH = directory / "data" / "instances.json"
    with threadpool_limits(limits=1):
        if args.action == "gate":
            report = teacher_gate()
            save(ARTIFACTS / "teacher_gate.json", report)
            print(json.dumps(report, indent=2))
        elif args.action == "train":
            train()
        else:
            evaluate()


if __name__ == "__main__":
    main()
