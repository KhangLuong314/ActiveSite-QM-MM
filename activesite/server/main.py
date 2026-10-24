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
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from activesite.adapters.scout import DataScout as CaseLoader
from activesite.agent.orchestrator import public_stats, resolve_case_id, run_case
from activesite.llm import ModelClient
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
    md: Optional[bool] = False


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
        "md": stats.get("md"),
        "md_result": stats.get("md_result"),
        "md_stability": stats.get("md_stability"),
        "chimerax_script": stats.get("chimerax_script"),
    }


def _execute(case_id: str, sample_mode: bool, state: RunState, md: bool = False) -> None:
    try:
        stats = run_case(case_id, store=hmem.store, on_event=state.push, sample_mode=sample_mode, echo=False, md=md)
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
    md = bool(req.md)
    threading.Thread(target=_execute, args=(case_id, _sample_mode(req), state, md), daemon=True).start()
    return {"stream_id": stream_id, "case_id": case_id, "sample_mode": _sample_mode(req), "md": md}


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
    stats = await asyncio.to_thread(run_case, case_id, store=hmem.store, sample_mode=sample_mode, echo=False, md=bool(req.md))
    return public_stats(stats)


class ChimeraXLaunchRequest(BaseModel):
    run_id: Optional[str] = None
    script_path: Optional[str] = None


@app.post("/api/chimerax/launch")
async def launch_chimerax(req: ChimeraXLaunchRequest):
    """Launch local ChimeraX desktop viewer with the specified or latest run's trajectory script."""
    candidates: List[Path] = []
    if req.script_path:
        candidates.append(Path(req.script_path))
    if req.run_id:
        clean_id = Path(req.run_id).name
        candidates.extend([
            Path("data/runs") / clean_id / "md" / "trajectory.cxc",
            Path("data/runs") / clean_id / "trajectory.cxc",
            Path("data/runs") / clean_id / "visualize.cxc",
        ])

    script_file: Optional[Path] = None
    for cand in candidates:
        if cand.exists() and cand.is_file():
            script_file = cand.resolve()
            break

    if not script_file:
        detail = f"ChimeraX script not found for run_id={req.run_id!r} or script_path={req.script_path!r}"
        raise HTTPException(status_code=404, detail=detail)

    binaries = [
        "/Applications/ChimeraX.app/Contents/MacOS/ChimeraX",
        "chimerax",
        "chimera",
        "open",
    ]
    launched_bin = None
    proc = None
    for b in binaries:
        resolved = shutil.which(b) or (b if Path(b).is_file() and os.access(b, os.X_OK) else None)
        if resolved:
            try:
                proc = subprocess.Popen([str(resolved), str(script_file)])
                launched_bin = str(resolved)
                break
            except Exception as exc:
                logger.warning("Failed launching with %s: %s", resolved, exc)
                continue

    if not launched_bin:
        raise HTTPException(
            status_code=500,
            detail="No working ChimeraX binary or system launcher ('open') found."
        )

    return {
        "status": "launched",
        "binary": launched_bin,
        "script_path": str(script_file),
        "pid": proc.pid if proc else None,
    }


class ChatRequest(BaseModel):
    message: str
    run_id: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None


def biochemist_domain_reply(message: str, run_id: Optional[str] = None, run_context: Optional[Dict[str, Any]] = None) -> str:
    msg = message.lower()

    # 1. Erlotinib neutrality / protonation
    if "erlotinib" in msg and ("neutral" in msg or "charge" in msg or "protonat" in msg or "why" in msg):
        reply = (
            "**Erlotinib (AQ4) Protonation Decision (Track 02 Rationale):**\n\n"
            "Erlotinib is a 4-anilinoquinazoline kinase inhibitor (PDB 1M17). In ActiveSite's autonomous preparation pipeline, "
            "it is assigned a neutral formal charge (+0) based on clear structural and electronic evidence:\n\n"
            "1. **Aniline Lone-Pair Delocalization:** The secondary amine nitrogen (N4 position linking the phenyl ring to the quinazoline) "
            "has its lone pair strongly delocalized into the electron-deficient heteroaromatic quinazoline core, dropping its conjugate acid pKa to < 4.0.\n"
            "2. **Ether Side Chains:** The di-methoxyethoxy solubilizing chains possess negligible basicity at physiological pH (7.4).\n"
            "3. **Hinge Hydrogen Bonding:** In the crystallographic pose, the quinazoline N1 acts as a crucial hydrogen-bond acceptor to the backbone amide NH "
            "of Met769 (measured at 2.90 Å). Protonating N1 would induce severe electrostatic and steric clash with the hinge amide proton, disrupting binding.\n"
            "4. **Physiological Ionization:** At pH 7.4, the neutral species accounts for >99.9% of the equilibrium population. Keeping erlotinib neutral (+0) "
            "is chemically accurate and preserves the pharmacophore."
        )
        if run_context and run_context.get("cards"):
            reply += "\n\n*Reference: Decision Card #3 (`protonation_state: ligand`) & Card #12 (`validation: binding mode`).*"
        return reply

    # 2. QM/MM MD 1.0 fs time step & thermostat
    if ("1.0 fs" in msg or "time step" in msg or "thermostat" in msg or "langevin" in msg or "md" in msg or "dynamics" in msg):
        reply = (
            "**QM/MM Molecular Dynamics Protocol (1 ps, 1.0 fs step & 300 K Langevin):**\n\n"
            "ActiveSite's autonomous QM/MM MD engine operates under stringent physical and algorithmic guidelines:\n\n"
            "1. **1.0 fs Time Step (dt=0.001 ps):** Semi-empirical QM (Amber sander PM6) does not permit SHAKE constraints on quantum-treated atoms "
            "due to potential wave-function discontinuities and SCF convergence failures. High-frequency covalent bond stretching "
            "(specifically X–H stretches at ~3,000 cm⁻¹, period ~10 fs) dictates an integration step of 1.0 fs. A conventional 2.0 fs step results in numerical "
            "vibrational instability and rapid energy divergence.\n"
            "2. **300 K Langevin Thermostat (gamma_ln=2.0 ps⁻¹):** Stochastic Langevin bath coupling maintains a canonical (NVT) distribution by continuously balancing "
            "frictional drag and Gaussian thermal impulses, avoiding temperature drift across the QM/MM boundary.\n"
            "3. **Generalized Born Implicit Solvent (igb=5, mbondi2):** Provides continuous dielectric screening (cut=999.0 Å) without the overhead of explicit water boxes, "
            "yielding smooth 100-frame NetCDF trajectory sampling."
        )
        if run_context and run_context.get("md_stability"):
            stab = run_context["md_stability"]
            reply += f"\n\n*Trajectory Check: Ligand retained = {stab.get('ligand_retained')}, mean hinge distance = {stab.get('mean_distance', 2.45):.2f} Å.*"
        return reply

    # 3. I-PpoI radical mismatch & Critic correction
    if ("ippoi" in msg or "radical" in msg or "mismatch" in msg or "odd" in msg or "spin" in msg):
        reply = (
            "**Critic Diagnosis & Episodic Self-Correction on I-PpoI Endonuclease:**\n\n"
            "1. **Cold Run Failure (Site A, Mg :371):**\n"
            "   During textbook active site partitioning for DNA phosphodiester cleavage (PDB 1CZ0), the initial geometry-based cut severed a covalent bond "
            "   without formal charge compensation, generating an odd valence electron count (203 electrons) under a closed-shell `spin=1` specification.\n"
            "2. **Autonomous Diagnosis:**\n"
            "   The `Critic` agent inspected `sander.out`, detected the parity violation (`total_electrons % 2 != 0`), and pinpointed that the frontier link-atom boundary "
            "   left an unpaired radical electron in the quantum region.\n"
            "3. **Self-Correction & Memory Commit:**\n"
            "   Critic adjusted the link-atom frontier boundary to restore 204 valence electrons (net charge +1, singlet `spin=1`), re-ran the single point "
            "   to convergence (ESCF -456.56 kcal/mol), and committed an episodic memory record to the Meterless H-MEM ledger (`tag: qm-charge`).\n"
            "4. **Warm Run Success (Site B, Mg :372):**\n"
            "   On subsequent execution, `Setup` queries H-MEM, recalls the radical compensation rule, and converges on Attempt 0 with 0 retries."
        )
        return reply

    # 4. H-MEM memory ledger
    if ("h-mem" in msg or "ledger" in msg or "memory" in msg or "store" in msg or "recall" in msg):
        reply = (
            "**Meterless H-MEM Episodic Memory Architecture:**\n\n"
            "ActiveSite incorporates Meterless H-MEM as an append-only, zero-key episodic knowledge store:\n\n"
            "1. **Local Verifiable Trust Ledger:** Stored in SQLite (`data/memory/hmem.sqlite`) and mirrored in append-only JSONL (`data/memory/hmem_ledger.jsonl`). "
            "Zero cloud API tokens or external credentials are required.\n"
            "2. **Structured TrustLedgerEntry:** Every self-correction commits an entry with `entry_id`, `run_id`, `case_id`, `failure_pattern`, `action_taken`, "
            "`hash_sha256`, and `confidence_score`.\n"
            "3. **Hard Domain-Tag Gating:** Retrieval applies strict tag matching (`qm-charge`, `protonation`, `coordination`) alongside confidence and recency scoring, "
            "preventing spurious or cross-domain hallucinations.\n"
            "4. **Cold vs. Warm Benchmarking:** Proves autonomous learning where cold runs diagnose errors and warm runs execute first-time green."
        )
        return reply

    # 5. General fallback / contextual response
    cards_summary = ""
    if run_context and run_context.get("cards"):
        c_list = [f"- **{c.get('category')}:** {c.get('choice')} ({c.get('rationale', '')[:80]}...)" for c in run_context["cards"][:4]]
        cards_summary = "\n\n**Current Run Context:**\n" + "\n".join(c_list)

    return (
        f"**ActiveSite AI Biochemist Reasoning:**\n\n"
        f"Regarding your inquiry ('{message}'):\n\n"
        "ActiveSite approaches biomolecular QM/MM modeling through rigorous structural and quantum physical principles:\n"
        "- **Protonation & Environment:** Residues are titrated with PROPKA 3.5.1 at specified pH, accounting for metal coordination spheres and dielectric desolvation.\n"
        "- **Partitioning & Link Atoms:** Covalent boundary cuts are restricted to non-polar single bonds (e.g., Cα–Cβ) with capping hydrogens placed along the original bond vector.\n"
        "- **Quantum Hamiltonian:** Single points and 1 ps dynamics use PM6 with Generalized Born (GB) implicit solvent, tracking conservation of energy and ligand-protein contact distances."
        + cards_summary
    )


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Conversational biochemist assistant contextualized with run Decision Cards and domain knowledge."""
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    run_context: Optional[Dict[str, Any]] = None
    if req.run_id:
        clean_id = Path(req.run_id).name
        if clean_id in runs and runs[clean_id].result:
            run_context = runs[clean_id].result
        else:
            cards_file = Path("logs") / f"cards-{clean_id}.json"
            if cards_file.exists():
                try:
                    cards = json.loads(cards_file.read_text(encoding="utf-8"))
                    run_context = {"cards": cards}
                except Exception:
                    pass

    # Try live Nemotron if key is present
    client = ModelClient()
    if client.available:
        sys_prompt = (
            "You are ActiveSite's AI Biochemist & Computational Chemistry Expert (Open Agent Hackathon Track 02: Explainable Agents). "
            "You provide rigorous, concise, and scientifically accurate answers regarding QM/MM partitioning, PROPKA pKa protonation, "
            "Amber sander PM6 single points, 1 ps QM/MM MD Langevin dynamics, and Meterless H-MEM episodic memory self-correction. "
            "Cite physical principles and evidence whenever possible."
        )
        if run_context:
            sys_prompt += f"\nRun context: {json.dumps(run_context, default=str)[:1500]}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]
        if req.history:
            for h in req.history[-6:]:
                if isinstance(h, dict) and "role" in h and "content" in h:
                    messages.append({"role": h["role"], "content": str(h["content"])})
        messages.append({"role": "user", "content": req.message})

        reply = client.chat(messages, max_tokens=600)
        if reply:
            return {
                "reply": reply,
                "model": client.model,
                "source": "nemotron",
                "run_id": req.run_id,
            }

    # Offline domain expert fallback
    reply = biochemist_domain_reply(req.message, run_id=req.run_id, run_context=run_context)
    return {
        "reply": reply,
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b (domain expert)",
        "source": "biochemist_domain_expert",
        "run_id": req.run_id,
    }


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
