"""Check the running local API using a published example, never private data."""

import json
from pathlib import Path
import time

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    with httpx.Client(base_url="http://127.0.0.1:8774", timeout=10) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        model = client.get("/api/model")
        model.raise_for_status()
        assert model.json()["ready"]
        instance = client.get("/api/examples").json()["examples"][0]
        response = client.post("/api/runs", json={"instance": instance, "solver_seconds": 1})
        assert response.status_code == 202, response.text
        identifier = response.json()["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{identifier}").json()
            if run["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert run["status"] == "completed", run
        assert len(run["results"]) == 5
        assert all(result["validation"]["valid"] for result in run["results"])
        assert next(result for result in run["results"] if result["method"] == "cp_sat")["makespan"] == 11
        exported = client.get(f"/api/runs/{identifier}/export")
        exported.raise_for_status()
        assert "attachment" in exported.headers["content-disposition"]
        assert exported.json()["run"]["instance"] == instance
        record = {"health": health.json(), "model_version": model.json()["version"],
                  "methods": [{key: row[key] for key in ("method", "status", "makespan", "wall_seconds")} for row in run["results"]],
                  "export_matches_input": True}
        (root / "outputs/api-smoke.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
