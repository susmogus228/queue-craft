"""Static instances and an independent, algorithm-agnostic schedule validator."""

from dataclasses import dataclass
import re


def _object(value, keys, path):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{path}: expected exactly {', '.join(keys)}")


def _integer(value, low, high, path):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{path}: expected an integer from {low} to {high}")
    return value


@dataclass(frozen=True)
class Operation:
    id: str
    job_id: str
    job: int
    index: int
    machine: int
    duration: int


@dataclass(frozen=True)
class Job:
    id: str
    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class Instance:
    name: str
    machines: int
    jobs: tuple[Job, ...]

    @classmethod
    def from_dict(cls, data):
        _object(data, ("name", "machines", "jobs"), "instance")
        name = data["name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("name: use 1..80 nonempty characters")
        machines = _integer(data["machines"], 1, 12, "machines")
        raw_jobs = data["jobs"]
        if not isinstance(raw_jobs, list) or not 1 <= len(raw_jobs) <= 24:
            raise ValueError("jobs: provide 1..24 jobs")
        jobs, ids, total = [], set(), 0
        for j, raw in enumerate(raw_jobs):
            _object(raw, ("id", "operations"), f"jobs[{j}]")
            job_id = raw["id"]
            if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", job_id) or job_id in ids:
                raise ValueError(f"jobs[{j}].id: use a unique 1..24 character alphanumeric ID, underscore or hyphen")
            ids.add(job_id)
            entries = raw["operations"]
            if not isinstance(entries, list) or not 1 <= len(entries) <= 12:
                raise ValueError(f"jobs[{j}].operations: provide 1..12 operations")
            operations = []
            for k, item in enumerate(entries):
                _object(item, ("machine", "duration"), f"jobs[{j}].operations[{k}]")
                machine = _integer(item["machine"], 0, machines - 1, f"jobs[{j}].operations[{k}].machine")
                duration = _integer(item["duration"], 1, 1000, f"jobs[{j}].operations[{k}].duration")
                operations.append(Operation(f"{job_id}.{k + 1}", job_id, j, k, machine, duration))
            total += len(operations)
            jobs.append(Job(job_id, tuple(operations)))
        if total > 144:
            raise ValueError("jobs: at most 144 operations are allowed")
        return cls(name.strip(), machines, tuple(jobs))

    @property
    def operations(self):
        return tuple(op for job in self.jobs for op in job.operations)

    @property
    def horizon(self):
        return sum(op.duration for op in self.operations)

    @property
    def lower_bound(self):
        machine_loads = [0] * self.machines
        for op in self.operations:
            machine_loads[op.machine] += op.duration
        return max(max(machine_loads), max(sum(op.duration for op in job.operations) for job in self.jobs))

    def to_dict(self):
        return {"name": self.name, "machines": self.machines, "jobs": [
            {"id": job.id, "operations": [{"machine": op.machine, "duration": op.duration} for op in job.operations]}
            for job in self.jobs
        ]}


def validate_schedule(instance: Instance, operations: list[dict]) -> dict:
    """Check original operation identity, arithmetic, precedence and exclusivity.

    This deliberately does not use dispatch state or CP-SAT variables.
    """
    if not isinstance(operations, list):
        return {"valid": False, "errors": ["Schedule must be a list of operations"]}
    expected = {op.id: op for op in instance.operations}
    seen, usable, lanes, errors = set(), {}, [[] for _ in range(instance.machines)], []
    for row in operations:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            errors.append("Malformed operation record")
            continue
        operation_id = row["id"]
        if operation_id not in expected:
            errors.append(f"Unknown operation {operation_id}")
            continue
        if operation_id in seen:
            errors.append(f"Duplicate operation {operation_id}")
            continue
        seen.add(operation_id)
        op = expected[operation_id]
        if row.get("job_id") != op.job_id or type(row.get("index")) is not int or row["index"] != op.index:
            errors.append(f"Incorrect identity for {operation_id}")
        if type(row.get("machine")) is not int or row["machine"] != op.machine:
            errors.append(f"Incorrect machine for {operation_id}")
        if type(row.get("duration")) is not int or row["duration"] != op.duration:
            errors.append(f"Incorrect duration for {operation_id}")
        start, end = row.get("start"), row.get("end")
        if type(start) is not int or type(end) is not int or start < 0 or end - start != op.duration:
            errors.append(f"Invalid time interval for {operation_id}")
            continue
        usable[operation_id] = (start, end)
        lanes[op.machine].append((start, end, operation_id))
    missing = set(expected) - seen
    if missing:
        errors.append("Missing operations: " + ", ".join(sorted(missing)))
    for job in instance.jobs:
        for before, after in zip(job.operations, job.operations[1:]):
            if before.id in usable and after.id in usable and usable[after.id][0] < usable[before.id][1]:
                errors.append(f"Precedence violated: {before.id} before {after.id}")
    for machine, rows in enumerate(lanes):
        ordered = sorted(rows)
        for before, after in zip(ordered, ordered[1:]):
            if after[0] < before[1]:
                errors.append(f"Machine M{machine + 1} overlap: {before[2]} / {after[2]}")
    return {"valid": not errors, "errors": errors}
