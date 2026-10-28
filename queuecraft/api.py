"""Local HTTP transport and bounded, ephemeral comparison jobs.

Computation lives in service.py. Imported problems never enter training or leave
this process. Run one uvicorn worker: this in-memory queue is intentionally local.
"""

from __future__ import annotations

import copy
import html
import importlib
import json
import logging
import math
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 128 * 1024
STRATEGIES = ("fifo", "spt", "mwkr", "learned", "cp_sat")
TERMINAL = frozenset(("completed", "failed", "cancelled"))
Method = Literal["fifo", "spt", "mwkr", "learned", "cp_sat"]
StrictInteger = Annotated[int, Field(strict=True)]
ProblemName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80)]
JobID = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{1,24}$")]


def get_model_info() -> dict:
    return importlib.import_module("queuecraft.service").get_model_info()


def list_examples() -> list[dict]:
    return importlib.import_module("queuecraft.service").list_examples()


def run_comparison(instance: dict, strategies: list[str], **options) -> list[dict]:
    return importlib.import_module("queuecraft.service").run_comparison(instance, strategies, **options)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OperationInput(StrictModel):
    machine: Annotated[StrictInteger, Field(ge=0, le=11)]
    duration: Annotated[StrictInteger, Field(ge=1, le=1000)]


class JobInput(StrictModel):
    id: JobID
    operations: Annotated[list[OperationInput], Field(min_length=1, max_length=12)]


class InstanceInput(StrictModel):
    name: ProblemName
    machines: Annotated[StrictInteger, Field(ge=1, le=12)]
    jobs: Annotated[list[JobInput], Field(min_length=1, max_length=24)]

    @model_validator(mode="after")
    def consistent_instance(self):
        if len({job.id for job in self.jobs}) != len(self.jobs):
            raise ValueError("Job IDs must be unique")
        if sum(len(job.operations) for job in self.jobs) > 144:
            raise ValueError("A problem may contain at most 144 operations")
        if any(op.machine >= self.machines for job in self.jobs for op in job.operations):
            raise ValueError("Operation machine must be smaller than machines")
        return self


class RunInput(StrictModel):
    instance: InstanceInput
    strategies: Annotated[list[Method], Field(min_length=1, max_length=5)] = Field(default_factory=lambda: list(STRATEGIES))
    solver_seconds: Annotated[float, Field(ge=0.1, le=5.0, allow_inf_nan=False)] = 2.0

    @field_validator("strategies")
    @classmethod
    def unique_methods(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Strategies must not repeat")
        return value

    @field_validator("solver_seconds", mode="before")
    @classmethod
    def strict_budget(cls, value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Solver budget must be a finite number")
        return value


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object key")
        value[key] = item
    return value


class LocalRequestGuard:
    """Check actual streamed bytes before JSON decoding or allocating a job."""

    def __init__(self, app, allowed_origins: frozenset[str]):
        self.app = app
        self.allowed_origins = allowed_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        unsafe = scope["method"] not in ("GET", "HEAD", "OPTIONS")
        origin = headers.get(b"origin")
        if unsafe and origin is not None and origin.decode("latin-1") not in self.allowed_origins:
            response = JSONResponse({"detail": "Cross-site writes are not allowed", "code": "ORIGIN_REJECTED"}, status_code=403)
            return await response(scope, receive, send)

        buffered = None
        if unsafe:
            length = headers.get(b"content-length")
            if length is not None:
                try:
                    size = int(length)
                except ValueError:
                    return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
                if size < 0:
                    return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
                if size > MAX_BODY_BYTES:
                    return await JSONResponse({"detail": "JSON body exceeds 128 KiB", "code": "BODY_TOO_LARGE"}, status_code=413)(scope, receive, send)
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    return await JSONResponse({"detail": "JSON body exceeds 128 KiB", "code": "BODY_TOO_LARGE"}, status_code=413)(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            buffered = b"".join(chunks)
            if scope["method"] == "POST" and scope["path"] == "/api/runs":
                content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                if content_type != b"application/json" and not content_type.endswith(b"+json"):
                    return await JSONResponse({"detail": "Use Content-Type: application/json"}, status_code=415)(scope, receive, send)
                try:
                    json.loads(buffered, parse_constant=_reject_constant, object_pairs_hook=_unique_pairs)
                except (ValueError, UnicodeError, RecursionError):
                    return await JSONResponse({"detail": "Body must be valid JSON with unique keys and finite numbers", "code": "INVALID_JSON"}, status_code=400)(scope, receive, send)

        delivered = False

        async def replay_receive():
            nonlocal delivered
            if buffered is not None and not delivered:
                delivered = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        async def guarded_send(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.extend([(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer")])
                if scope["path"].startswith("/api/"):
                    response_headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": response_headers}
            await send(message)

        await self.app(scope, replay_receive, guarded_send)


@dataclass
class Run:
    id: str
    instance: dict
    strategies: list[str]
    solver_seconds: float
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_clock: float = field(default_factory=time.monotonic)
    status: str = "queued"
    results: list[dict] = field(default_factory=list)
    error: str | None = None
    finished_clock: float | None = None
    model: dict = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)

    def snapshot(self) -> dict:
        return copy.deepcopy({
            "id": self.id, "status": self.status, "created_at": self.created_at,
            "elapsed_seconds": round((self.finished_clock or time.monotonic()) - self.created_clock, 4),
            "instance": self.instance, "strategies": self.strategies, "solver_seconds": self.solver_seconds,
            "results": self.results, "error": self.error,
        })


class RunStore:
    def __init__(self, max_pending: int, max_retained: int, ttl_seconds: float):
        if min(max_pending, max_retained, ttl_seconds) <= 0:
            raise ValueError("Queue and retention limits must be positive")
        self.max_pending, self.max_retained, self.ttl = max_pending, max_retained, ttl_seconds
        self.condition = threading.Condition(threading.RLock())
        self.runs: dict[str, Run] = {}
        self.queue: deque[str] = deque()
        self.closed = False
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._work, name="queuecraft-comparison", daemon=True)
        self.thread.start()

    def close(self):
        with self.condition:
            self.closed = True
            for run in self.runs.values():
                if run.status not in TERMINAL:
                    run.cancel.set()
                    if run.status == "queued":
                        run.status = "cancelled"
                        run.finished_clock = time.monotonic()
            self.queue.clear()
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=6)

    def _prune(self):
        now = time.monotonic()
        expired = [key for key, run in self.runs.items() if run.finished_clock is not None and now - run.finished_clock >= self.ttl]
        for key in expired:
            del self.runs[key]

    def submit(self, request: RunInput) -> dict:
        with self.condition:
            self._prune()
            if self.closed:
                raise HTTPException(503, "Comparison worker is shutting down")
            if sum(run.status not in TERMINAL for run in self.runs.values()) >= self.max_pending:
                raise HTTPException(429, "Comparison queue is full; wait or cancel a run", headers={"Retry-After": "2"})
            while len(self.runs) >= self.max_retained:
                removable = next((key for key, run in self.runs.items() if run.status in TERMINAL), None)
                if removable is None:
                    raise HTTPException(429, "Run storage is full; cancel an active run", headers={"Retry-After": "2"})
                del self.runs[removable]
            run = Run(id=uuid.uuid4().hex, instance=request.instance.model_dump(), strategies=list(request.strategies), solver_seconds=request.solver_seconds)
            self.runs[run.id] = run
            self.queue.append(run.id)
            snapshot = run.snapshot()
            self.condition.notify()
            return snapshot

    def _find(self, run_id: str) -> Run:
        self._prune()
        run = self.runs.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found or expired")
        return run

    def get(self, run_id: str) -> dict:
        with self.condition:
            return self._find(run_id).snapshot()

    def cancel_or_remove(self, run_id: str) -> dict:
        with self.condition:
            run = self._find(run_id)
            if run.status in TERMINAL:
                del self.runs[run_id]
                return {"id": run_id, "status": "removed"}
            run.cancel.set()
            if run.status == "queued":
                run.status = "cancelled"
                run.finished_clock = time.monotonic()
                # Remove the identifier as well as freeing the pending slot.
                # Otherwise repeated enqueue/cancel while a solver runs could
                # grow this deque beyond both configured storage limits.
                self.queue.remove(run_id)
            return run.snapshot()

    def export(self, run_id: str) -> dict:
        with self.condition:
            run = self._find(run_id)
            if not run.results:
                raise HTTPException(409, "This run has no results to export yet")
            return copy.deepcopy({"schema_version": "1.0", "exported_at": datetime.now(timezone.utc).isoformat(), "run": run.snapshot(), "model": run.model})

    def _work(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or bool(self.queue), timeout=min(self.ttl, 1.0))
                self._prune()
                if self.closed:
                    return
                if not self.queue:
                    continue
                run = self.runs.get(self.queue.popleft())
                if run is None or run.status != "queued":
                    continue
                run.status = "running"
            try:
                try:
                    model = get_model_info()
                except Exception:
                    model = {"ready": False, "version": None, "error": "Model metadata unavailable"}
                with self.condition:
                    run.model = copy.deepcopy(model)
                for method in run.strategies:
                    if run.cancel.is_set():
                        break
                    try:
                        results = run_comparison(copy.deepcopy(run.instance), [method], solver_seconds=run.solver_seconds, cancel_event=run.cancel)
                    except Exception:
                        LOGGER.exception("Comparison method failed: method=%s run=%s", method, run.id)
                        results = [{"method": method, "label": method, "status": "ERROR", "makespan": None, "wall_seconds": 0.0, "best_bound": None, "optimality_proven": False, "operations": [], "trace": [], "validation": {"valid": False, "errors": []}, "error": "Strategy failed; see local server log"}]
                    with self.condition:
                        run.results.extend(copy.deepcopy(results))
                with self.condition:
                    run.status = "cancelled" if run.cancel.is_set() else "completed"
                    run.finished_clock = time.monotonic()
            except Exception:
                LOGGER.exception("Run failed: run=%s", run.id)
                with self.condition:
                    run.status = "failed"
                    run.error = "Comparison failed; completed method results remain available"
                    run.finished_clock = time.monotonic()


def _research_page() -> str:
    try:
        metadata = get_model_info()
    except Exception:
        metadata = {"ready": False, "note": "Model metadata is unavailable. No measured model results can be displayed."}
    try:
        source_items = json.loads((PROJECT_ROOT / "docs" / "SOURCES.json").read_text(encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        source_items = []
    links = "".join(f'<li><a href="{html.escape(item["url"], quote=True)}" rel="noreferrer">{html.escape(item["title"])}</a></li>' for item in source_items if str(item.get("url", "")).startswith("https://"))
    details = html.escape(json.dumps(metadata, indent=2, ensure_ascii=False))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>QueueCraft research</title>
<style>body{{background:#0f0f0f;color:#eee;font:17px/1.6 system-ui;margin:0}}main{{max-width:1000px;margin:auto;padding:32px 24px}}a{{color:#67dfb1}}pre{{overflow:auto;padding:20px;background:#1a1a1a;border:1px solid #333;font-size:13px}}h1,h2{{line-height:1.2}}li{{margin:8px 0}}</style>
<main><a href="/">Back to QueueCraft</a><h1>QueueCraft research</h1>
<p>A local comparison of fixed dispatch rules, a trained operation scorer and a bounded mathematical solver.</p>
<h2>What the model learns</h2><p>The scorer learns priorities from generated training problems and partial schedules. Learned scores rank candidate operations; they are not probabilities of optimality. Inference does not train on imported jobs.</p>
<h2>How results are checked</h2><p>Evaluation must split whole problems before creating decision states. Every output schedule is checked for job precedence, complete operation coverage and machine overlap. Compare finished schedules and computation time, including the model's losses against FIFO, shortest processing time and most work remaining.</p>
<h2>Limits</h2><p>Static known durations, fixed machines and non-preemptive work. No due dates, breakdowns, stock or live factory control. FEASIBLE does not prove optimality. The solver budget and best bound matter. Synthetic problem results do not establish performance in a real factory.</p>
<h2>Model and measured results</h2><p>This section uses current model metadata; unavailable results remain unavailable.</p><pre>{details}</pre>
<h2>Primary sources</h2><ul>{links}</ul><p><a href="/api/model">Model JSON</a> · <a href="/docs">API reference</a></p></main></html>'''


def create_app(*, max_pending: int = 4, max_retained: int = 16, ttl_seconds: float = 1800, static_dir: Path | None = None, allowed_origins: set[str] | None = None) -> FastAPI:
    store = RunStore(max_pending, max_retained, ttl_seconds)
    web_root = (static_dir or PROJECT_ROOT / "web" / "dist").resolve()

    @asynccontextmanager
    async def lifespan(application):
        store.start()
        yield
        store.close()

    application = FastAPI(title="QueueCraft API", version="0.1.0", description="Local, bounded scheduling comparisons. Imported instances are temporary and are not used for training.", lifespan=lifespan)
    application.state.run_store = store
    origins = allowed_origins if allowed_origins is not None else {"http://127.0.0.1:8774", "http://localhost:8774", "http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:5174", "http://localhost:5174"}
    application.add_middleware(LocalRequestGuard, allowed_origins=frozenset(origins))
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @application.exception_handler(RequestValidationError)
    async def safe_validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in exc.errors()]
        return JSONResponse({"detail": details}, status_code=422)

    @application.get("/api/health")
    def health():
        try:
            ready = bool(get_model_info().get("ready", False))
        except Exception:
            ready = False
        return {"status": "ok", "model_ready": ready}

    @application.get("/api/model")
    def model_info():
        try:
            return get_model_info()
        except Exception:
            raise HTTPException(503, "Model metadata is unavailable") from None

    @application.get("/api/examples")
    def examples():
        try:
            return {"examples": list_examples()}
        except Exception:
            raise HTTPException(503, "Example problems are unavailable") from None

    @application.post("/api/runs", status_code=202)
    def submit_run(body: RunInput):
        return store.submit(body)

    @application.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return store.get(run_id)

    @application.delete("/api/runs/{run_id}")
    def delete_run(run_id: str):
        return store.cancel_or_remove(run_id)

    @application.get("/api/runs/{run_id}/export")
    def export_run(run_id: str):
        exported = store.export(run_id)
        return JSONResponse(exported, headers={"Content-Disposition": f'attachment; filename="queuecraft-{exported["run"]["id"]}.json"'})

    @application.get("/research", response_class=HTMLResponse)
    def research():
        return _research_page()

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        relative = Path(path)
        if path.startswith("api/") or any(part.startswith(".") for part in relative.parts):
            raise HTTPException(404, "Not found")
        candidate = (web_root / relative).resolve()
        if not candidate.is_relative_to(web_root):
            raise HTTPException(404, "Not found")
        permitted = {".js", ".css", ".svg", ".png", ".webp", ".ico", ".woff2", ".woff", ".json"}
        if candidate.is_file() and candidate.suffix.lower() in permitted:
            return FileResponse(candidate)
        index = web_root / "index.html"
        if path in ("", "plan", "compare") and index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "Frontend is not built; run npm install and npm run build in web" if not path else "Not found")

    return application


app = create_app()
