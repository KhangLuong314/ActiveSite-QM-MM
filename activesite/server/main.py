"""ActiveSite — FastAPI Interactive Server with SSE Thought Streaming.

Provides REST and Server-Sent Events endpoints for running explainable QM/MM simulations,
inspecting Track 02 Decision Cards, downloading ChimeraX scripts, and auditing the Meterless Trust Ledger.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from activesite.adapters.scout import DataScout
from activesite.agent.orchestrator import MasterOrchestrator, WorkflowOutput
from activesite.memory.meterless import MeterlessHMEM

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ActiveSite — Autonomous QM/MM Assistant",
    description="Track 02: 'The Agent That Can Explain Why' (Open Agent Hackathon 2026)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hmem = MeterlessHMEM()
orchestrator = MasterOrchestrator(hmem=hmem, sample_mode=True)
scout = DataScout()

# In-memory store for active streaming queues
active_streams: Dict[str, asyncio.Queue] = {}


class SimulationRequest(BaseModel):
    case_id: Optional[str] = None
    prompt: Optional[str] = None
    ph: Optional[float] = 7.4
    cutoff_radius: Optional[float] = 4.0
    qm_theory: Optional[str] = "PM6"
    sample_mode: bool = True


@app.get("/api/cases")
async def list_cases():
    """List all available benchmark cases with descriptions."""
    case_names = scout.list_benchmark_cases()
    results = []
    for name in case_names:
        try:
            data = scout.load_benchmark_case(name)
            results.append({
                "id": data.get("id", name),
                "system": data.get("system", name),
                "ligand": data.get("ligand", ""),
                "site": data.get("site", "A"),
                "question": data.get("question", ""),
                "ph": data.get("ph", 7.4),
            })
        except Exception as exc:
            logger.warning("Could not load case %s: %s", name, exc)
    return {"cases": results}


@app.get("/api/ledger")
async def get_ledger():
    """Retrieve the Meterless H-MEM Trust Ledger and episodic memory records."""
    records = hmem.query_memories()
    ledger = hmem.get_ledger()
    return {
        "records": [r.model_dump() for r in records],
        "ledger": [l.model_dump() for l in ledger],
    }


@app.post("/api/run")
async def run_simulation(req: SimulationRequest):
    """Execute a QM/MM simulation setup and return full Track 02 explanations."""
    stream_id = f"stream_{int(asyncio.get_event_loop().time() * 1000)}"
    q: asyncio.Queue = asyncio.Queue()
    active_streams[stream_id] = q

    def event_callback(stage: str, msg: str):
        try:
            q.put_nowait({"stage": stage, "message": msg})
        except Exception:
            pass

    try:
        orch = MasterOrchestrator(hmem=hmem, sample_mode=req.sample_mode)
        if req.case_id:
            output = orch.run_case(req.case_id, on_event=event_callback)
        elif req.prompt:
            output = orch.run_query(req.prompt, on_event=event_callback)
        else:
            raise HTTPException(status_code=400, detail="Either 'case_id' or 'prompt' must be provided.")

        q.put_nowait({"stage": "done", "message": "Simulation completed."})

        return {
            "success": output.success,
            "system_name": output.system_name,
            "stream_id": stream_id,
            "energy_kcal_mol": output.result.energy_kcal_mol,
            "energy_hartree": output.result.energy_hartree,
            "qm_theory": output.result.qm_theory,
            "qm_charge": output.partition.qm_charge,
            "spin_multiplicity": output.partition.spin_multiplicity,
            "valence_electrons": output.partition.total_valence_electrons,
            "execution_time_seconds": output.result.execution_time_seconds,
            "decision_cards": [c.model_dump() for c in output.decision_cards],
            "chimerax_script_path": output.chimerax_script_path,
            "report_markdown": output.report_markdown,
            "logs": output.logs,
            "qm_mask": output.partition.amber_qmmask,
            "num_link_atoms": len(output.partition.link_atoms),
        }
    except Exception as exc:
        logger.error("Simulation run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stream/{stream_id}")
async def stream_thoughts(stream_id: str):
    """Server-Sent Events endpoint streaming live thought logs."""
    q = active_streams.get(stream_id)

    async def event_generator():
        if not q:
            yield f"data: {json.dumps({'stage': 'info', 'message': 'Stream connected.'})}\n\n"
            return

        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("stage") == "done":
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'stage': 'ping', 'message': 'keep-alive'})}\n\n"
            except Exception:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/chimerax/{system_name}")
async def download_chimerax_script(system_name: str):
    """Download generated ChimeraX .cxc script."""
    cxc_path = Path("data/runs") / system_name / "visualize.cxc"
    if not cxc_path.exists():
        raise HTTPException(status_code=404, detail="ChimeraX script not found for this system.")
    return FileResponse(cxc_path, filename=f"{system_name}_activesite.cxc", media_type="text/plain")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the single-page web UI dashboard."""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>ActiveSite QM/MM Assistant</h1><p>UI loading...</p>"


def main():
    """Launch the ActiveSite web server using uvicorn."""
    import uvicorn
    uvicorn.run("activesite.server.main:app", host="0.0.0.0", port=8088, reload=False)


if __name__ == "__main__":
    main()
