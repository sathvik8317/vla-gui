"""FastAPI service: POST /run kicks off a task run in a background thread and
returns immediately with a run_id; GET /runs/{id} returns that run's current
RunRecord (in progress or finished); GET /runs/{id}/stream sends each
StepRecord as an SSE event as the run happens. Powers the Phase 8 demo.

Orchestrator.run()/run_streaming() are synchronous (Playwright + Ollama HTTP
calls, not async), so a run is driven from a plain daemon thread rather than
rewriting the agent loop as async — the run must not block the request that
starts it.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .browser import Executor
from .config import settings
from .eval.harness import load_tasks
from .orchestrate import Orchestrator
from .schema import RunRecord, StepRecord

RUNS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "runs"

app = FastAPI(title="vlagui")

_runs: dict[str, RunRecord] = {}
_queues: dict[str, "Queue[StepRecord | dict | None]"] = {}
_lock = threading.Lock()


class RunRequest(BaseModel):
    task_id: str | None = None  # matches an id in tasks/*.yaml
    url: str | None = None  # or an ad-hoc task: url + instruction + task_assertion
    instruction: str | None = None
    task_assertion: str | None = None
    max_steps: int = 6


class RunStarted(BaseModel):
    run_id: str


def _resolve_task(req: RunRequest) -> tuple[str, str, str, bool]:
    """Returns (url, instruction, task_assertion, is_todomvc)."""
    if req.task_id:
        task = next((t for t in load_tasks() if t.id == req.task_id), None)
        if task is None:
            raise HTTPException(404, f"unknown task_id {req.task_id!r}")
        return task.url, task.instruction, task.task_assertion, task.app == "todomvc"
    if not (req.url and req.instruction and req.task_assertion):
        raise HTTPException(400, "provide task_id, or url + instruction + task_assertion")
    return req.url, req.instruction, req.task_assertion, False


def _execute(run_id: str, url: str, instruction: str, task_assertion: str, is_todomvc: bool, max_steps: int) -> None:
    queue = _queues[run_id]
    try:
        with Executor(url) as ex:
            if is_todomvc:
                ex.reset()
            orch = Orchestrator(ex, run_dir=RUNS_DIR / run_id)
            for item in orch.run_streaming(instruction, task_assertion, max_steps):
                queue.put(item)
                with _lock:
                    if isinstance(item, StepRecord):
                        _runs[run_id].steps.append(item)
                    else:
                        _runs[run_id].outcome = item["outcome"]
                        _runs[run_id].termination_reason = item["termination_reason"]
    except Exception as e:
        with _lock:
            _runs[run_id].outcome = "failure"
            _runs[run_id].termination_reason = f"error: {e}"
    finally:
        with _lock:
            _runs[run_id].ended_at = datetime.now(timezone.utc)
        queue.put(None)  # sentinel: stream done


@app.post("/run", status_code=202)
def start_run(req: RunRequest) -> RunStarted:
    url, instruction, task_assertion, is_todomvc = _resolve_task(req)
    run_id = str(uuid.uuid4())
    with _lock:
        _runs[run_id] = RunRecord(
            run_id=run_id,
            task_id=req.task_id or instruction,
            model=settings.grounder_model,
            started_at=datetime.now(timezone.utc),
            steps=[],
        )
        _queues[run_id] = Queue()

    thread = threading.Thread(
        target=_execute, args=(run_id, url, instruction, task_assertion, is_todomvc, req.max_steps), daemon=True
    )
    thread.start()
    return RunStarted(run_id=run_id)


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> RunRecord:
    with _lock:
        record = _runs.get(run_id)
    if record is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")
    return record


@app.get("/runs/{run_id}/stream")
def stream_run(run_id: str) -> StreamingResponse:
    queue = _queues.get(run_id)
    if queue is None:
        raise HTTPException(404, f"unknown run_id {run_id!r}")

    def event_source():
        while True:
            try:
                item: Any = queue.get(timeout=30)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                yield "event: done\ndata: {}\n\n"
                break
            data = item.model_dump_json() if isinstance(item, StepRecord) else json.dumps(item)
            yield f"data: {data}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
