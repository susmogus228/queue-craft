"""A shared serial dispatcher and a separately validated CP-SAT reference."""

from copy import deepcopy
import math
import threading
import time

from .domain import Instance, validate_schedule


FEATURE_NAMES = (
    "duration", "remaining_work", "successor_work", "earliest_start",
    "earliest_finish", "job_ready", "machine_ready", "machine_work_left",
    "job_progress", "remaining_fraction", "machine_wait", "job_wait",
    "job_count", "machine_count", "machine_busy_fraction",
)

LABELS = {"fifo": "FIFO", "spt": "Shortest processing time", "mwkr": "Most work remaining", "learned": "Learned policy", "cp_sat": "CP-SAT", "teacher": "Teacher replay"}


class DispatchState:
    """Append-only serial schedule generation; a head is eligible for planning.

    All unfinished job heads can be selected, even if their feasible start is in
    the future. This is offline construction, not non-delay real-time execution.
    """

    def __init__(self, instance: Instance, record_trace=True):
        self.instance = instance
        self.next_index = [0] * len(instance.jobs)
        self.job_ready = [0] * len(instance.jobs)
        self.machine_ready = [0] * instance.machines
        self.machine_work = [0] * instance.machines
        self.machine_done = [0] * instance.machines
        self.remaining = instance.horizon
        self.scale = instance.lower_bound
        self.total_work = instance.horizon
        self.operations = []
        self.trace = []
        self.record_trace = record_trace
        self.suffixes = []
        for job in instance.jobs:
            suffix = [0] * (len(job.operations) + 1)
            for k in reversed(range(len(job.operations))):
                suffix[k] = suffix[k + 1] + job.operations[k].duration
                self.machine_work[job.operations[k].machine] += job.operations[k].duration
            self.suffixes.append(suffix)

    def clone(self):
        result = object.__new__(DispatchState)
        result.__dict__ = self.__dict__.copy()
        for name in ("next_index", "job_ready", "machine_ready", "machine_work", "machine_done", "operations"):
            setattr(result, name, list(getattr(self, name)))
        result.record_trace = False
        result.trace = []
        return result

    def candidates(self):
        values, scale = [], self.scale
        for j, job in enumerate(self.instance.jobs):
            index = self.next_index[j]
            if index == len(job.operations):
                continue
            op = job.operations[index]
            machine_ready, job_ready = self.machine_ready[op.machine], self.job_ready[j]
            start = max(machine_ready, job_ready)
            remaining_work = self.suffixes[j][index]
            raw_features = (
                op.duration / scale, remaining_work / scale, (remaining_work - op.duration) / scale,
                start / scale, (start + op.duration) / scale, job_ready / scale,
                machine_ready / scale, self.machine_work[op.machine] / scale,
                index / len(job.operations), self.remaining / self.total_work,
                max(0, job_ready - machine_ready) / scale,
                max(0, machine_ready - job_ready) / scale,
                len(self.instance.jobs) / 10, self.instance.machines / 10,
                self.machine_done[op.machine] / max(1, machine_ready),
            )
            values.append({"id": op.id, "job_id": op.job_id, "job": j, "index": index,
                           "machine": op.machine, "duration": op.duration,
                           "earliest_start": start, "remaining_work": remaining_work,
                           "score": None, "features": dict(zip(FEATURE_NAMES, raw_features))})
        return values

    def append(self, chosen, candidates=None):
        j = chosen["job"]
        op = self.instance.jobs[j].operations[self.next_index[j]]
        if op.id != chosen["id"]:
            raise ValueError("The chosen operation is not an eligible job head")
        start = max(self.machine_ready[op.machine], self.job_ready[j])
        end = start + op.duration
        step = len(self.operations) + 1
        self.operations.append({"id": op.id, "job_id": op.job_id, "index": op.index,
                                "machine": op.machine, "duration": op.duration,
                                "start": start, "end": end, "step": step})
        if self.record_trace:
            self.trace.append({"step": step, "chosen_id": op.id,
                               "candidates": [{k: v for k, v in row.items() if k != "job"} for row in (candidates or self.candidates())]})
        self.job_ready[j] = self.machine_ready[op.machine] = end
        self.next_index[j] += 1
        self.machine_work[op.machine] -= op.duration
        self.machine_done[op.machine] += op.duration
        self.remaining -= op.duration


def empty_result(method, status, error=None):
    return {"method": method, "label": LABELS.get(method, method), "status": status,
            "makespan": None, "wall_seconds": 0.0, "best_bound": None,
            "optimality_proven": False, "operations": [], "trace": [],
            "validation": {"valid": False, "errors": []}, "error": error}


def _result(instance, method, operations, trace, started):
    result = empty_result(method, "FEASIBLE")
    result.update(operations=operations, trace=trace, makespan=max(row["end"] for row in operations),
                  validation=validate_schedule(instance, operations), best_bound=instance.lower_bound)
    if not result["validation"]["valid"]:
        result.update(status="ERROR", error="Independent schedule validation failed")
    result["wall_seconds"] = time.perf_counter() - started
    return result


def dispatch(instance, method, scorer=None, cancel_event=None, forced_order=None, record_trace=True):
    started = time.perf_counter()
    state = DispatchState(instance, record_trace)
    while state.remaining:
        if cancel_event is not None and cancel_event.is_set():
            return empty_result(method, "CANCELLED")
        candidates = state.candidates()
        if forced_order is not None:
            chosen = min(candidates, key=lambda row: forced_order[row["id"]])
        elif method == "fifo":
            chosen = min(candidates, key=lambda row: (state.job_ready[row["job"]], row["job"]))
        elif method == "spt":
            chosen = min(candidates, key=lambda row: (row["duration"], row["earliest_start"], row["job"]))
        elif method == "mwkr":
            chosen = min(candidates, key=lambda row: (-row["remaining_work"], row["earliest_start"], row["duration"], row["job"]))
        elif method == "learned":
            if scorer is None:
                return empty_result(method, "UNAVAILABLE", "The trained scorer is unavailable; baseline strategies remain usable.")
            scores = list(scorer(candidates))
            if len(scores) != len(candidates) or not all(math.isfinite(float(value)) for value in scores):
                raise ValueError("Model returned invalid ranking scores")
            for row, score in zip(candidates, scores):
                row["score"] = float(score)
            chosen = min(candidates, key=lambda row: (-row["score"], row["earliest_start"], row["duration"], row["job"]))
        else:
            raise ValueError(f"Unknown dispatch strategy: {method}")
        state.append(chosen, candidates)
    return _result(instance, method, state.operations, state.trace, started)


def solve_cp(instance, seconds=2.0, cancel_event=None):
    from ortools.sat.python import cp_model

    started = time.perf_counter()
    if cancel_event is not None and cancel_event.is_set():
        return empty_result("cp_sat", "CANCELLED")
    if not math.isfinite(seconds) or not 0 < seconds <= 5:
        raise ValueError("Solver budget must be in (0, 5] seconds")
    model = cp_model.CpModel()
    tasks, lanes = {}, [[] for _ in range(instance.machines)]
    horizon = instance.horizon
    for job in instance.jobs:
        for op in job.operations:
            start = model.new_int_var(0, horizon, f"s_{op.id}")
            end = model.new_int_var(0, horizon, f"e_{op.id}")
            interval = model.new_interval_var(start, op.duration, end, op.id)
            tasks[op.id] = (start, end)
            lanes[op.machine].append(interval)
        for before, after in zip(job.operations, job.operations[1:]):
            model.add(tasks[before.id][1] <= tasks[after.id][0])
    for intervals in lanes:
        model.add_no_overlap(intervals)
    cost = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(cost, [tasks[job.operations[-1].id][1] for job in instance.jobs])
    model.minimize(cost)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    done = threading.Event()
    watcher = None
    if cancel_event is not None:
        def watch():
            while not done.wait(0.03):
                if cancel_event.is_set():
                    solver.stop_search()
                    return
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
    try:
        status = solver.solve(model)
    finally:
        done.set()
        if watcher:
            watcher.join(timeout=0.1)
    if cancel_event is not None and cancel_event.is_set():
        return empty_result("cp_sat", "CANCELLED")
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        result = empty_result("cp_sat", solver.status_name(status), "No schedule was returned within this solve.")
        result["wall_seconds"] = time.perf_counter() - started
        return result
    operations = [{"id": op.id, "job_id": op.job_id, "index": op.index,
                   "machine": op.machine, "duration": op.duration,
                   "start": int(solver.value(tasks[op.id][0])),
                   "end": int(solver.value(tasks[op.id][1])), "step": 0} for op in instance.operations]
    operations.sort(key=lambda row: (row["start"], row["job_id"], row["index"]))
    for step, row in enumerate(operations, 1):
        row["step"] = step
    result = _result(instance, "cp_sat", operations, [], started)
    if result["validation"]["valid"]:
        result.update(status=solver.status_name(status), best_bound=float(solver.best_objective_bound),
                      optimality_proven=status == cp_model.OPTIMAL)
    return result


def replay_teacher(instance, reference):
    """Left-shift the teacher's machine order in the shared serial generator."""
    if not reference.get("validation", {}).get("valid"):
        raise ValueError("Teacher schedule must pass independent validation")
    order = {row["id"]: (row["start"], row["end"], row["id"]) for row in reference["operations"]}
    replay = dispatch(instance, "teacher", forced_order=order)
    if not replay["validation"]["valid"] or replay["makespan"] > reference["makespan"]:
        raise ValueError("Teacher replay is incompatible with the serial schedule generator")
    return replay
