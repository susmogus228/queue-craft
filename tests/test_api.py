"""HTTP/job lifecycle tests; fake computation isolates the transport contract."""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from queuecraft import api


EXAMPLE = {
    "name": "Small workshop",
    "machines": 2,
    "jobs": [
        {"id": "J1", "operations": [{"machine": 0, "duration": 3}]},
        {"id": "J2", "operations": [{"machine": 1, "duration": 2}]},
    ],
}


def result(method="fifo"):
    return {
        "method": method,
        "label": method,
        "status": "FEASIBLE",
        "makespan": 3,
        "wall_seconds": 0.001,
        "best_bound": None,
        "optimality_proven": False,
        "operations": [],
        "trace": [],
        "validation": {"valid": True, "errors": []},
        "error": None,
    }


@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(api, "get_model_info", lambda: {
        "ready": False, "version": None, "feature_names": [],
        "training_summary": {}, "evaluation": {}, "limitations": ["Test service."],
    })
    monkeypatch.setattr(api, "list_examples", lambda: [copy.deepcopy(EXAMPLE)])
    monkeypatch.setattr(api, "run_comparison", lambda instance, strategies, **kw: [result(strategies[0])])


@contextmanager
def client_for(**options):
    app = api.create_app(**options)
    with TestClient(app) as client:
        yield client


def finished(client, run_id, timeout=3):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.01)
    pytest.fail("Comparison did not finish within the transport-test budget")


def start(client, strategies=None, instance=None, **options):
    payload = {"instance": copy.deepcopy(instance or EXAMPLE), **options}
    if strategies is not None:
        payload["strategies"] = strategies
    return client.post("/api/runs", json=payload)


def test_health_examples_model_and_openapi_without_model(services):
    with client_for() as client:
        assert client.get("/api/health").json() == {"status": "ok", "model_ready": False}
        assert client.get("/api/model").json()["ready"] is False
        assert client.get("/api/examples").json() == {"examples": [EXAMPLE]}
        schema = client.get("/openapi.json").json()
        assert "/api/runs/{run_id}/export" in schema["paths"]
        assert client.get("/docs").status_code == 200


def test_run_retains_original_input_and_exports_actual_results(services):
    with client_for() as client:
        created = start(client, ["fifo", "spt"])
        assert created.status_code == 202
        run_id = created.json()["id"]
        run = finished(client, run_id)
        assert run["status"] == "completed"
        assert [row["method"] for row in run["results"]] == ["fifo", "spt"]
        assert run["instance"] == EXAMPLE
        assert run["elapsed_seconds"] >= 0
        assert "progress" not in run
        exported = client.get(f"/api/runs/{run_id}/export")
        assert exported.status_code == 200
        assert "attachment" in exported.headers["content-disposition"]
        assert exported.json()["run"]["instance"] == EXAMPLE
        assert exported.json()["run"]["results"] == run["results"]
        assert exported.json()["model"]["ready"] is False
        assert client.delete(f"/api/runs/{run_id}").json()["status"] == "removed"
        assert client.get(f"/api/runs/{run_id}").status_code == 404


@pytest.mark.parametrize("field,value", [
    ("machines", True), ("machines", 1.5), ("machines", 0), ("machines", 13),
    ("name", "   "), ("name", "x" * 81), ("unknown", "field"),
])
def test_strict_instance_fields(services, field, value):
    problem = copy.deepcopy(EXAMPLE)
    problem[field] = value
    with client_for() as client:
        assert start(client, instance=problem).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("duration", True), ("duration", 1.5), ("duration", 0), ("duration", 1001),
    ("machine", True), ("machine", -1), ("machine", 2), ("extra", 3),
])
def test_strict_operation_fields(services, field, value):
    problem = copy.deepcopy(EXAMPLE)
    problem["jobs"][0]["operations"][0][field] = value
    with client_for() as client:
        assert start(client, instance=problem).status_code == 422


def test_duplicate_ids_and_operation_count_limit(services):
    with client_for() as client:
        problem = copy.deepcopy(EXAMPLE)
        problem["jobs"][1]["id"] = "J1"
        assert start(client, instance=problem).status_code == 422
        problem["jobs"] = [{"id": f"J{i}", "operations": [{"machine": 0, "duration": 1}] * 12} for i in range(13)]
        assert start(client, instance=problem).status_code == 422
        problem["jobs"] = [{"id": "bad/id", "operations": [{"machine": 0, "duration": 1}]}]
        assert start(client, instance=problem).status_code == 422


@pytest.mark.parametrize("options", [
    {"strategies": []}, {"strategies": ["fifo", "fifo"]}, {"strategies": ["fake"]},
    {"solver_seconds": True}, {"solver_seconds": 0}, {"solver_seconds": 5.1},
    {"solver_seconds": "2"}, {"extra": "no"},
])
def test_strict_run_configuration(services, options):
    with client_for() as client:
        assert start(client, **options).status_code == 422


def test_invalid_json_content_type_and_constants(services):
    with client_for() as client:
        assert client.post("/api/runs", content="not json", headers={"Content-Type": "application/json"}).status_code == 400
        assert client.post("/api/runs", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post("/api/runs", content='{"instance":NaN}', headers={"Content-Type": "application/json"}).status_code == 400
        assert client.post("/api/runs", content='{"instance":{},"instance":{}}', headers={"Content-Type": "application/json"}).status_code == 400


def test_cross_site_write_and_unknown_host_are_rejected(services):
    with client_for() as client:
        assert client.post("/api/runs", json={"instance": EXAMPLE}, headers={"Origin": "https://attacker.invalid"}).status_code == 403
        assert client.delete("/api/runs/nope", headers={"Origin": "null"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "attacker.invalid"}).status_code == 400
        assert start(client, ["fifo"]).status_code == 202
        assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"


def test_content_limit_including_missing_content_length(services):
    with client_for() as client:
        response = client.post("/api/runs", content=(b"x" * 140000), headers={"Content-Type": "application/json"})
        assert response.status_code == 413

    app = api.create_app()
    messages = iter([
        {"type": "http.request", "body": b"x" * 70000, "more_body": True},
        {"type": "http.request", "body": b"x" * 70000, "more_body": False},
    ])
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "path": "/api/runs", "raw_path": b"/api/runs", "root_path": "", "query_string": b"", "scheme": "http", "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")], "client": ("127.0.0.1", 1234), "server": ("testserver", 80)}
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 413


def test_queue_is_bounded_and_queued_cancellation_is_immediate(services, monkeypatch):
    active = threading.Event()
    release = threading.Event()

    def blocked(instance, strategies, **kwargs):
        active.set()
        release.wait(2)
        return [result(strategies[0])]

    monkeypatch.setattr(api, "run_comparison", blocked)
    try:
        with client_for(max_pending=2) as client:
            first = start(client, ["fifo"]).json()
            assert active.wait(1)
            assert client.get(f"/api/runs/{first['id']}/export").status_code == 409
            queued = start(client, ["spt"]).json()
            assert start(client, ["mwkr"]).status_code == 429
            cancelled = client.delete(f"/api/runs/{queued['id']}").json()
            assert cancelled["status"] == "cancelled"
            release.set()
            assert finished(client, first["id"])["status"] == "completed"
            assert finished(client, queued["id"])["status"] == "cancelled"
    finally:
        release.set()


def test_running_cancellation_preserves_completed_methods(services, monkeypatch):
    second_active = threading.Event()

    def runner(instance, strategies, cancel_event=None, **kwargs):
        if strategies[0] == "spt":
            second_active.set()
            assert cancel_event is not None
            cancel_event.wait(2)
            return []
        return [result(strategies[0])]

    monkeypatch.setattr(api, "run_comparison", runner)
    with client_for() as client:
        created = start(client, ["fifo", "spt", "mwkr"]).json()
        assert second_active.wait(1)
        response = client.delete(f"/api/runs/{created['id']}")
        assert response.status_code == 200
        run = finished(client, created["id"])
        assert run["status"] == "cancelled"
        assert [row["method"] for row in run["results"]] == ["fifo"]
        assert client.get(f"/api/runs/{created['id']}/export").status_code == 200


def test_cancelled_queue_entries_do_not_accumulate(services, monkeypatch):
    active = threading.Event()
    release = threading.Event()

    def blocked(instance, strategies, **kwargs):
        active.set()
        release.wait(3)
        return [result(strategies[0])]

    monkeypatch.setattr(api, "run_comparison", blocked)
    try:
        with client_for(max_pending=2, max_retained=3) as client:
            start(client, ["fifo"])
            assert active.wait(1)
            for _ in range(10):
                queued = start(client, ["spt"])
                assert queued.status_code == 202
                client.delete(f"/api/runs/{queued.json()['id']}")
            assert len(client.app.state.run_store.queue) == 0
            release.set()
    finally:
        release.set()


def test_one_strategy_failure_does_not_hide_other_results(services, monkeypatch):
    def runner(instance, strategies, **kwargs):
        if strategies[0] == "spt":
            raise RuntimeError("Private internal path must not leak")
        return [result(strategies[0])]

    monkeypatch.setattr(api, "run_comparison", runner)
    with client_for() as client:
        run = finished(client, start(client, ["fifo", "spt", "mwkr"]).json()["id"])
        assert [row["status"] for row in run["results"]] == ["FEASIBLE", "ERROR", "FEASIBLE"]
        assert "Private internal" not in json.dumps(run)


def test_empty_export_unknown_run_retention_and_expiry(services, monkeypatch):
    with client_for(max_retained=2, ttl_seconds=0.04) as client:
        assert client.get("/api/runs/missing").status_code == 404
        assert client.get("/api/runs/missing/export").status_code == 404
        first = start(client, ["fifo"]).json()["id"]
        finished(client, first)
        time.sleep(0.06)
        assert client.get(f"/api/runs/{first}").status_code == 404
    with client_for(max_retained=2) as client:
        identifiers = []
        for _ in range(3):
            identifier = start(client, ["fifo"]).json()["id"]
            finished(client, identifier)
            identifiers.append(identifier)
        assert client.get(f"/api/runs/{identifiers[0]}").status_code == 404
        assert client.get(f"/api/runs/{identifiers[-1]}").status_code == 200


def test_research_and_api_not_found_do_not_return_spa(services):
    with client_for() as client:
        assert client.get("/research").status_code == 200
        assert "No measured" in client.get("/research").text or "Model" in client.get("/research").text
        assert client.get("/api/does-not-exist").status_code == 404
        assert client.get("/api/does-not-exist").headers["content-type"].startswith("application/json")
        assert client.get("/.env").status_code == 404


def test_static_server_only_exposes_build_artifacts(services, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>QueueCraft build</title>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('build')", encoding="utf-8")
    (tmp_path / ".env").write_text("private", encoding="utf-8")
    (tmp_path / "source.py").write_text("private", encoding="utf-8")
    with client_for(static_dir=tmp_path) as client:
        assert "QueueCraft build" in client.get("/").text
        assert client.get("/assets/app.js").text == "console.log('build')"
        assert client.get("/.env").status_code == 404
        assert client.get("/source.py").status_code == 404
        assert client.get("/api/nonexistent").status_code == 404
        assert "QueueCraft build" not in client.get("/api/nonexistent").text


def test_snapshot_and_export_preserve_actual_solver_budget(services):
    with client_for() as client:
        created = start(client, ["fifo"], solver_seconds=0.7)
        run = finished(client, created.json()["id"])
        assert run["solver_seconds"] == 0.7
        assert client.get(f"/api/runs/{run['id']}/export").json()["run"]["solver_seconds"] == 0.7


def test_idle_retention_releases_expired_data_without_a_new_request(services):
    with client_for(ttl_seconds=0.03) as client:
        run = finished(client, start(client, ["fifo"]).json()["id"])
        deadline = time.monotonic() + 0.6
        store = client.app.state.run_store
        while time.monotonic() < deadline:
            with store.condition:
                removed = run["id"] not in store.runs
            if removed:
                break
            time.sleep(0.01)
        assert removed
