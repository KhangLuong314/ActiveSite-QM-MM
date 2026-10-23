"""ActiveSite — FastAPI server: live SSE run feed, memory, data-layer SQL, judge endpoint.

POST /api/run starts the orchestrator in a worker thread and returns a stream
id at once; GET /api/stream/{id} replays and follows the Trace entries as
"step" events and ends with one "result" event. Nothing in the UI is a number
the stream did not carry.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from activesite.adapters.scout import DataScout as CaseLoader
from activesite.agent import orchestrator as orch
from activesite.agent.orchestrator import public_stats, resolve_case_id, run_case
from activesite.memory.meterless import MeterlessHMEM

logger = logging.getLogger(__name__)

app = FastAPI(title="ActiveSite — Autonomous QM/MM Assistant",
              description="Track 02: 'The Agent That Can Explain Why' (Open Agent Hackathon 2026)", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

hmem = MeterlessHMEM()
loader = CaseLoader()
PING_SECONDS = 15.0
LEDGER_TAIL = 50


class RunState:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.done = threading.Event()
        self.cond = threading.Condition()

    def push(self, entry: Dict[str, Any]) -> None:
        with self.cond:
            self.events.append(entry)
            self.cond.notify_all()

    def finish(self, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        with self.cond:
            self.result, self.error = result, error
            self.done.set()
            self.cond.notify_all()


runs: Dict[str, RunState] = {}


class SimulationRequest(BaseModel):
    case_id: Optional[str] = None
    prompt: Optional[str] = None
    sample_mode: Optional[bool] = None


def _sample_mode(req: SimulationRequest) -> bool:
    if req.sample_mode is not None:
        return bool(req.sample_mode)
    return os.getenv("SAMPLE_MODE", "true").lower() in ("true", "1", "yes")


def _case_id(req: SimulationRequest) -> str:
    if req.case_id:
        if req.case_id not in loader.list_benchmark_cases():
            raise HTTPException(status_code=404, detail=f"unknown case {req.case_id!r}")
        return req.case_id
    if req.prompt:
        try:
            return resolve_case_id(req.prompt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=400, detail="Either 'case_id' or 'prompt' must be provided.")


def _result_payload(stats: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "stats": public_stats(stats),
        "cards": [c.model_dump() for c in stats.get("_cards", [])],
        "validation": stats.get("validation"),
        "checks": stats.get("checks"),
        "result": {k: v for k, v in (stats.get("_result") or {}).items() if k != "command"},
        "sql": stats.get("sql"),
        "report_markdown": stats.get("_report_markdown", ""),
    }


def _execute(case_id: str, sample_mode: bool, state: RunState) -> None:
    try:
        stats = run_case(case_id, store=hmem.store, on_event=state.push, sample_mode=sample_mode, echo=False)
        state.finish(result=_result_payload(stats))
    except Exception as exc:  # the stream must end with something honest
        logger.error("run failed: %s", exc, exc_info=True)
        state.finish(error=f"{type(exc).__name__}: {exc}")


@app.get("/api/cases")
async def list_cases():
    results = []
    for name in loader.list_benchmark_cases():
        try:
            d = loader.load_benchmark_case(name)
            results.append({"id": d.get("id", name), "system": d.get("system", name), "kind": d.get("kind", "metal"),
                            "ligand": d.get("ligand", ""), "site": d.get("site", "A"), "question": d.get("question", ""),
                            "ph": d.get("ph")})
        except Exception as exc:
            logger.warning("Could not load case %s: %s", name, exc)
    return {"cases": results}


@app.post("/api/run")
async def start_run(req: SimulationRequest):
    case_id = _case_id(req)
    stream_id = f"stream_{int(time.time() * 1000)}_{len(runs)}"
    state = RunState()
    runs[stream_id] = state
    threading.Thread(target=_execute, args=(case_id, _sample_mode(req), state), daemon=True).start()
    return {"stream_id": stream_id, "case_id": case_id, "sample_mode": _sample_mode(req)}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _stream(stream_id: str):
    state = runs.get(stream_id)
    if state is None:
        yield _sse("error", {"message": f"unknown stream {stream_id}"})
        return
    sent = 0
    last_ping = time.monotonic()
    while True:
        events = list(state.events)
        for entry in events[sent:]:
            yield _sse("step", entry)
        sent = len(events)
        if state.done.is_set() and sent == len(state.events):
            if state.error:
                yield _sse("error", {"message": state.error})
            else:
                yield _sse("result", state.result)
            return
        if time.monotonic() - last_ping > PING_SECONDS:
            yield _sse("ping", {"t": time.time()})
            last_ping = time.monotonic()
        await asyncio.sleep(0.2)


@app.get("/api/stream/{stream_id}")
async def stream_run(stream_id: str):
    return StreamingResponse(_stream(stream_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/run/stream")
async def stream_alias(stream_id: str):
    return await stream_run(stream_id)


@app.post("/run")
async def run_sync(req: SimulationRequest):
    """Judge endpoint: synchronous, returns the same JSON as `run.py --case <id> --json`."""
    case_id = _case_id(req)
    sample_mode = _sample_mode(req)
    stats = await asyncio.to_thread(run_case, case_id, store=hmem.store, sample_mode=sample_mode, echo=False)
    return public_stats(stats)


@app.get("/api/ledger")
async def get_ledger():
    memories = hmem.store.all()
    ledger = hmem.store.read_ledger()
    return {"memories": memories, "ledger": ledger[-LEDGER_TAIL:], "ledger_total": len(ledger),
            "records": [r.model_dump() for r in hmem.query_memories()], "db": str(hmem.db_path), "ledger_path": str(hmem.ledger_path)}


@app.post("/api/memory/reset")
async def reset_memory():
    global hmem
    removed = []
    hmem.store.close()
    for path in (hmem.db_path, hmem.ledger_path):
        if Path(path).exists():
            Path(path).unlink()
            removed.append(str(path))
    hmem = MeterlessHMEM(db_path=hmem.db_path, ledger_path=hmem.ledger_path)
    return {"removed": removed, "memories": len(hmem.store.all()), "ledger": len(hmem.store.read_ledger())}


@app.get("/api/chimerax/{run_id}")
async def download_chimerax_script(run_id: str):
    cxc = Path("data/runs") / run_id / "visualize.cxc"
    if not cxc.exists():
        raise HTTPException(status_code=404, detail="no ChimeraX script for this run (not generated by the loop yet)")
    return FileResponse(cxc, filename=f"{run_id}.cxc", media_type="text/plain")


@app.get("/api/trace/{run_id}")
async def download_trace(run_id: str):
    path = Path("logs") / f"trace-{run_id}.jsonl"
    if not path.exists() or "/" in run_id or ".." in run_id:
        raise HTTPException(status_code=404, detail="trace not found")
    return FileResponse(path, filename=path.name, media_type="application/x-ndjson")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>ActiveSite QM/MM Assistant</h1><p>UI missing</p>"


def main():
    import uvicorn
    uvicorn.run("activesite.server.main:app", host="0.0.0.0", port=8088, reload=False)


if __name__ == "__main__":
    main()
